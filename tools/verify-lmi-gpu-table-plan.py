"""Mode30: HFI DMA, every extra RX page and read-only performance table plan."""
from pathlib import Path
import re,runpy
def verify(log,firmware,window=None):
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-hfi-io.py')))['verify'](log,firmware,window)
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    assert rows('LMI_GPU_PLAN_SPEED_BIN',1)==[0]
    assert rows('LMI_GPU_RX_PAGES',3)==[0x7eadb003,0x7eadb000,0x7eadb001]
    perf=rows('LMI_GPU_PERF_PLAN',59)
    raw=rows('LMI_GPU_PLAN_ARCS',54);arcs=[]
    for n in range(3):
        address,count,*values=raw[n*18:(n+1)*18]
        assert address&3==0 and address>>16&7==3 and 2<=count<=16
        assert values[0]==0 and all(a<b for a,b in zip(values[:count-1],values[1:count])) and values[count:]==[0]*(16-count)
        arcs.append(values[:count])
    assert len({raw[0],raw[18],raw[36]})==3
    bcm=rows('LMI_GPU_PLAN_BCM',4);assert len(set(bcm))==4 and all(a&3==0 and a>>16&7==5 for a in bcm)
    def vote(pri,mx,level):
        k=next(k for k,v in enumerate(pri) if v>=level)
        j=next((j for j,v in enumerate(mx) if v>=pri[k]),len(mx)-1)
        return pri[k]<<16|j<<8|k
    assert perf[:3]==[0,8,2]
    levels=[0,64,128,144,192,224,256,320]
    for n,(level,khz) in enumerate(zip(levels,[0,305000,400000,441600,490000,525000,587000,670000])):
        value,acd,freq=perf[3+n*3:6+n*3]
        assert value==vote(arcs[0],arcs[2],level) and acd==0xffffffff and freq==khz
    assert perf[27:51]==[0]*24 and perf[51:]==[vote(arcs[1],arcs[2],0),0,vote(arcs[1],arcs[2],48),200000,0,0,0,0]
    assert rows('LMI_GPU_TABLE_PLAN_RESULT',1)==[1] and log.count('LMI_GPU_TABLE_PLAN_VERIFIED\n')==1
    order=['LMI_GPU_HFI_IO_RESULT','LMI_GPU_PLAN_SPEED_BIN','LMI_GPU_RX_PAGES','LMI_GPU_PLAN_ARCS','LMI_GPU_PLAN_BCM','LMI_GPU_PERF_PLAN','LMI_GPU_TABLE_PLAN_VERIFIED',
           'LMI_GPU_TABLE_PLAN_RESULT','LMI_GPU_GMU_BOOT_STATUS']
    positions=[log.index(m+'\n') for m in order];assert positions==sorted(positions)
    result.update(mode=30,additional_rx_pages_executed=True,performance_table_prepared=True,
                  performance_table=perf,arc_tables=arcs,bcm_addresses=bcm,performance_table_sent=False,gx_power_requested=False)
    return result
