import socket
import time
import threading
import sys
from matplotlib import pyplot as plt

# Initialization
msg_duplicate = set()
client = {}
server = set()
balance_log = {}
proposed_priority = 0
bandwidth_num = 0
bw_logger = []
time_logger = []
process_terminate = False
log_Delay = {}

# Use lock to ensure ordering
action_queue_lock = threading.Lock()
msg_duplicate_lock = threading.Lock()
send_lock = threading.Lock()
receive_lock = threading.Lock()
balance_log_lock = threading.Lock()
proposed_priority_lock = threading.Lock()
bandwidth_num_lock = threading.Lock()
log_Delay_lock = threading.Lock()

MessageSize = 1024
class Message:
    def __init__(self):
        self.Sender_Node = ""
        self.MessageID = ""
        self.Content = ""
        self.priority = (0, "")
        self.transmitable = False
        self.todo_Multicast = False

    def msg_set(self, msg_str):
        msg_list = msg_str.split('|')
        self.Sender_Node = msg_list[0]
        self.Content = msg_list[1]
        self.MessageID = msg_list[2]    
        self.priority = eval(msg_list[3])     
        self.transmitable = False

    def msg_to_string(self):
        info_str = "%s|%s|%s|%s" %(self.Sender_Node, self.Content, self.MessageID, self.priority)
        return info_str+"\0"*(MessageSize-len(info_str))

# Use ISIS queue with total ordering to represent action operation in acount
class Action:
    def __init__(self):
        self.queue = []
        self.fb_entries = dict() # A entry table to record the feedback

    def sort(self):
        self.queue.sort(key=msg_priority, reverse=True)
    
    def delete(self, msg_id):
        for msg in self.queue:
            if msg.MessageID == msg_id:
                self.queue.remove(msg)
                self.fb_entries.pop(msg_id)
        self.sort()

    def append(self, msg):
        self.queue.append(msg)
        self.fb_entries[msg.MessageID] = [1, (0, "")] # [receiving time, max priority]
        self.sort()

    def transmit(self):
        transmitted_msg = []
        while len(self.queue) != 0 and self.queue[-1].transmitable:
            self.fb_entries.pop(self.queue[-1].MessageID)
            transmitted_msg.append(self.queue.pop(-1))
        return transmitted_msg

    def update_transmitability(self, node_num, node_name):
        for msg in self.queue:
            if self.fb_entries[msg.MessageID][0] == node_num + 1:
                msg.transmitable = True
                # update the msg if it is the required node
                if msg.Sender_Node == node_name:
                    l = self.fb_entries[msg.MessageID]
                    msg.priority = max(l[1], msg.priority)
                    msg.todo_Multicast = True
        return

    def update_priority(self, new_msg, node_num, node_name):
        final_priority = -1
        if new_msg.MessageID not in self.fb_entries:
            return final_priority
        fd_list = self.fb_entries[new_msg.MessageID]
        fd_list[0] += 1 # Update the received time
        # Update if it is the required node
        if new_msg.Sender_Node == node_name:
            fd_list[1] = max(fd_list[1], new_msg.priority)
        # Update if it is the priority
        if fd_list[0] == node_num + 1:
            for msg in self.queue:
                if msg.MessageID == new_msg.MessageID:
                    msg.priority = max(fd_list[1], msg.priority)
                    final_priority = msg.priority
                    msg.transmitable = True
                    self.sort()
                    break
        return final_priority

action_queue = Action()

def msg_priority(msg):
    return msg.priority

def start_events(node_name):
    global action_queue
    global msg_duplicate
    global proposed_priority
    for line in sys.stdin:
        # Initialize the message
        msg = Message()
        msg.Sender_Node = node_name
        msg.Content = line.strip()
        msg.MessageID = node_name + str(time.time())
        proposed_priority_lock.acquire()
        proposed_priority += 1
        msg.priority = (proposed_priority, node_name)
        proposed_priority_lock.release()

        msg_duplicate_lock.acquire()
        msg_duplicate.add(msg.MessageID)
        msg_duplicate_lock.release()
        action_queue_lock.acquire()
        action_queue.append(msg)
        action_queue_lock.release()
        log_Delay_lock.acquire()
        log_Delay[msg.MessageID] = [time.time()]
        log_Delay_lock.release()
        multicast(msg, node_name)

def receive_message(s, node_name):
    global action_queue
    global msg_duplicate
    global server
    global proposed_priority
    global bandwidth_num
    while not process_terminate:
        data = s.recv(MessageSize).decode('utf-8')
        if not data:
            break
        while len(data) < MessageSize:
            data += s.recv(MessageSize-len(data)).decode('utf-8')

        # Log the bandwidth
        bandwidth_num_lock.acquire()
        bandwidth_num += len(data)
        bandwidth_num_lock.release()
        
        msg = Message()
        msg.msg_set(data.strip('\0'))
        # check whether the msg is duplicate
        msg_duplicate_lock.acquire()
        if msg.MessageID in msg_duplicate:
            msg_duplicate_lock.release()
            action_queue_lock.acquire()
            receive_lock.acquire()
            final_priority = action_queue.update_priority(msg, len(server), node_name)
            receive_lock.release()
            if final_priority != -1:
                transmit()
                action_queue_lock.release()
                proposed_priority_lock.acquire()
                proposed_priority = max(proposed_priority, final_priority[0])
                proposed_priority_lock.release()
                if node_name == msg.Sender_Node:
                    msg.priority = final_priority
                    log_Delay_lock.acquire()
                    log_Delay[msg.MessageID].append(time.time())
                    log_Delay_lock.release()
                    multicast(msg, node_name)
                continue
            action_queue_lock.release()
        else:
            proposed_priority_lock.acquire()
            proposed_priority += 1
            msg.priority = (proposed_priority, node_name)
            proposed_priority_lock.release()
            msg_duplicate.add(msg.MessageID)
            action_queue_lock.acquire()
            action_queue.append(msg)
            action_queue_lock.release()
            msg_duplicate_lock.release()
            multicast(msg, node_name)

    receive_lock.acquire()
    server.remove(s)
    node_num = len(server)
    s.close()
    failure_handler(node_num, node_name)
    receive_lock.release()
    return

def update_balances(msg_text):
    global balance_log
    split_msg = msg_text.split()
    operation = split_msg[0]

    if operation == "DEPOSIT":
        account = split_msg[1]
        fund = int(split_msg[2])
        balance_log_lock.acquire()
        if account in balance_log:
            balance_log[account] += fund
        else:
            balance_log[account] = fund
        balance_log_lock.release()

    elif operation == "TRANSFER":
        source = split_msg[1]
        destination = split_msg[3]
        fund = int(split_msg[4])
        if source not in balance_log:
            print("Invalid Account! The user account does not exist in the system!")
            return
        balance_log_lock.acquire()
        if balance_log[source] < fund:
            print("Invalid Transaction! The amount of transaction excceed the account's balance!")
            balance_log_lock.release()
            return
        balance_log[source] -= fund
        if destination in balance_log:
            balance_log[destination] += fund
        else:
            balance_log[destination] = fund
        balance_log_lock.release()
    else:
        print("Invalid Operation on the account!")
        return
    
    balance_msg = "BALANCES"
    balance_log_lock.acquire()
    sorted_accounts = sorted(balance_log.keys())
    for account in sorted_accounts:
        balance_msg += " %s:%d"%(account, balance_log[account])
    balance_log_lock.release()
    print(balance_msg)

def transmit():
    global action_queue
    transmitted_msg = action_queue.transmit()
    multicast_msg = []
    if len(transmitted_msg) == 0:
        return
    for msg in transmitted_msg:
        update_balances(msg.Content)
        if msg.todo_Multicast:
            multicast_msg.append(msg)
    # If some nodes failureed,changed the flag to indicate whether it can transmit
    for msg in multicast_msg:
        log_Delay_lock.acquire()
        log_Delay[msg.MessageID].append(time.time())
        log_Delay_lock.release()
        multicast_no_check(msg)

def multicast(msg, node_name):
    global client
    global action_queue
    for n in client.copy():
        todo_terminate = False
        if n not in client:
            continue
        s = client[n]
        try:
            numbyte = s.send(msg.msg_to_string().encode("utf-8"))
            if numbyte == 0:
                todo_terminate = True
        except:
            todo_terminate = True

        if todo_terminate: # TCP terminate
            send_lock.acquire()
            client.pop(n)
            node_num = len(client)
            s.close()
            failure_handler(node_num, node_name)
            send_lock.release()

def failure_handler(node_num, node_name):
    action_queue_lock.acquire()
    action_queue.update_transmitability(node_num, node_name)
    transmit()
    action_queue_lock.release()

def multicast_no_check(msg):
    global client
    for n in client.copy():
        if n not in client:
            continue
        s = client[n]
        try:
            s.send(msg.msg_to_string().encode("utf-8"))
        except:
            continue

def node_connect(id, addr, port):
    global client
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((addr, port))
            send_lock.acquire()
            client[id] = s
            send_lock.release()
            break
        except:
            continue

def read_config(file):
    f = open(file, "r")
    node_num = int(f.readline().strip())
    node_info = []
    for l in f:
        info = l.strip().split()
        info[2] = int(info[2])
        node_info.append(info)
    return node_num, node_info

def bandwidth_logger(time_interval):
    global bandwidth_num
    global bw_logger
    
    start_time = time.time()
    time_logger.append(0)
    while not process_terminate:
        time.sleep(time_interval)
        curr_time = time.time() - start_time
        time_diff = curr_time - time_logger[-1]
        time_logger.append(curr_time)
        bandwidth_num_lock.acquire()
        bw_logger.append(bandwidth_num/time_diff)
        bandwidth_num = 0
        bandwidth_num_lock.release()

def main():
    global process_terminate
    global server
    
    if len(sys.argv) != 4:
        print('Invalid input command argvs')
        sys.exit(0)
    ip = '127.0.0.1'
    node_name = sys.argv[1]
    port = int(sys.argv[2])
    config_fname = sys.argv[3]
    
    
    node_num, node_info = read_config(config_fname)

    # Nodes connection
    for info in node_info:
        connect_t = threading.Thread(target=node_connect, args=(info[0], info[1], info[2]))
        connect_t.start()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((ip, port))
    s.listen(64)
    while len(server) != node_num:
        sock, addr = s.accept()
        server.add(sock)

    # Check whether all nodes are connected
    while True:
        if len(client) == node_num:
            break
        else:
            continue

    # begin to receive message
    for i in server:
        receive_t = threading.Thread(target=receive_message, args=(i, node_name))
        receive_t.start()

    time_interval = 1
    process_bandwidth_logger = threading.Thread(target=bandwidth_logger, args=(time_interval,))
    process_bandwidth_logger.start()

    # Begin to send message
    ### Begin_run_time = time.time()
    ### While time.time()-Begin_run_time>100
    while True:
        try:
            start_events(node_name)
        except:
            process_terminate = True
            sorted_msg = sorted(log_Delay, key = lambda x:log_Delay[x][0])
            msg_delay = []
            for msg in sorted_msg:
                if len(log_Delay[msg]) == 2:
                    msg_delay.append(log_Delay[msg][1]-log_Delay[msg][0])

            plt.figure(figsize=(6,10))
            # figure for the bandwidth
            bandwidth_fig = plt.subplot(211)
            bandwidth_fig.plot(time_logger[1:], bw_logger)
            bandwidth_fig.set_title("Graph of the Bandwidth for "+node_name)
            bandwidth_fig.set_xlabel("T / s")
            bandwidth_fig.set_ylabel("Bw / Byte/s")
            # figure for the message delay
            delay_fig = plt.subplot(212)      
            delay_fig.plot(list(range(len(msg_delay))),msg_delay)
            delay_fig.set_title("Graph of the Message delay for "+node_name)
            delay_fig.set_xlabel("Msg / idx")
            delay_fig.set_ylabel("Delay / s")
            plt.savefig("./test/%s.png"%(node_name))

            break

if __name__ == "__main__":
    main()

    ### pass
