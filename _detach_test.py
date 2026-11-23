import time, os
open(r'G:/_setup/detach_test.txt','w').write('start pid=%d\n' % os.getpid())
for i in range(1, 7):
    time.sleep(20)
    open(r'G:/_setup/detach_test.txt','a').write('tick %d\n' % (i*20))
open(r'G:/_setup/detach_test.txt','a').write('done\n')
