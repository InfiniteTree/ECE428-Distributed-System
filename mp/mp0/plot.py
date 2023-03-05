import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


t=['0.1','0.2','0.3','0.4','0.5','0.6','0.7','0.8','0.9','1.0']
Ra=[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0]

maxdelay=[]
mindelay=[]
avgdelay=[]
maxband=[]
minband=[]
avgband=[]
for i in range(len(t)):
    f = "Ra{0}.csv".format(t[i])
    data=np.array(pd.read_csv(f,usecols=['node','delay[sec]','bandwidth[bytes/sec]']))
    delay=data[:,1]
    bandwidth=data[:,2]
    maxband.append(np.max(bandwidth))
    minband.append(np.min(bandwidth))
    avgband.append(np.mean(bandwidth))
    maxdelay.append(np.max(delay))
    mindelay.append(np.min(delay))
    avgdelay.append(np.mean(delay))


plt.figure(1)
L1,=plt.plot(Ra, maxdelay , color="r", linestyle="-", label='maxdelay')
L2,=plt.plot(Ra, mindelay , color="g", linestyle="-",label='mindelay')
L3,=plt.plot(Ra, avgdelay , color="b", linestyle="-",label='avgdelay')
plt.xlabel('Ra')
plt.ylabel('sec')
plt.legend(loc='upper left')
plt.savefig('./delay.jpg')


plt.figure(2)
L1,=plt.plot(Ra, maxband , color="r", linestyle="-",label="maxbandwidth")
L2,=plt.plot(Ra, minband , color="g", linestyle="-",label="minbandwidth")
L3,=plt.plot(Ra, avgband , color="b", linestyle="-",label="avgbandwidth")
plt.xlabel('Ra')
plt.ylabel('bytes/sec')
plt.legend(loc='upper left')

plt.savefig('./bandwidth.jpg')
