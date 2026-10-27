/* Actual A650 firmware executes the v68 register save/restore payloads.
 * The rasterizer, events, SMMU and caches are not emulated here. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "emu.h"
#include "util.h"
#include "lmi-gpu-blit-v68.c"
static void handle(struct emu *e,unsigned op,const uint32_t *args,unsigned count)
{
   unsigned table=e->instrs[1]&0xffff;
   e->gpr_regs.pc=e->instrs[table+op];
   e->waitin=false;e->branch_target=0;e->run_mode=true;
   assert(!e->roq.count);
   for(unsigned i=0;i<count;i++)assert(emu_queue_push(&e->roq,args[i]));
   emu_set_gpr_reg(e,REG_REM,count);
   unsigned steps=0;
   while(!e->waitin && steps<150){
      emu_step(e);steps++;
      /* Mesa does not implement A650's register authorization handshake
       * (control 0x5b), for these register access requests.
       * Model ONLY those fixed-function inputs; do not change firmware, its
       * instructions, payload, counts or the actual save/restore data. This
       * cannot establish that real CP_PROTECT authorizes these registers. */
      e->control_regs.val[0x5b]=1;
      assert(e->control_regs.val[0x27]<0x10000);
   }
   if(!e->waitin || e->roq.count)fprintf(stderr,"op=%x pc=%x steps=%u queue=%u rem=%u wait=%u\n",op,e->gpr_regs.pc,steps,e->roq.count,emu_get_gpr_reg(e,REG_REM),e->waitin);
   assert(e->waitin && !e->roq.count);
}
int main(int argc,char **argv)
{
   assert(argc==2);
   FILE *f=fopen(argv[1],"rb");assert(f);
   uint32_t fw[31632/4];assert(fread(fw,1,sizeof(fw),f)==sizeof(fw));fclose(f);
   assert(!afuc_util_init(afuc_get_fwid(fw[1]),&gpuver,false));
   struct emu e={.instrs=fw+1,.sizedwords=sizeof(fw)/4-1,
                 .fw_id=afuc_get_fwid(fw[1]),.quiet=true};
   emu_init(&e);
   uint32_t commands[1024];unsigned n=lmi_blit_commands(commands,0x20000000,0x30000000,0x40000000,4608);
   assert(n && n<1024);
   for(unsigned i=0;i<EMU_NUM_GPU_REGS;i++)e.gpu_regs.val[i]=(i*0x45d9f3bu)^0xa5a55a5a;
   uint32_t saved[EMU_NUM_GPU_REGS];memcpy(saved,e.gpu_regs.val,sizeof(saved));
   unsigned saves=0,restores=0;
   for(unsigned at=0;at<n;) {
      uint32_t h=commands[at++];unsigned count=h>>28==4?h&0x7f:h&0x3fff;
      unsigned op=(h>>16)&127;
      if(h>>28==7 && (op==0x3e || op==0x42)) {
         if(op==0x42 && !restores)
            for(unsigned i=0;i<EMU_NUM_GPU_REGS;i++)e.gpu_regs.val[i]=~saved[i];
         handle(&e,op,commands+at,count);
         if(op==0x3e)saves++;else restores++;
      }
      at+=count;
   }
   assert(saves==14 && restores==7);
   unsigned total=0;
   for(unsigned i=0;i<sizeof(ranges)/sizeof(ranges[0]);i++)
      for(unsigned j=0;j<ranges[i].count;j++) {
         unsigned reg=ranges[i].reg+j;
         assert(e.gpu_regs.val[reg]==saved[reg]);total++;
      }
   assert(total==21);
   emu_fini(&e);
   printf("PASS firmware handlers (modeled ready/success status): %u register values, %u save + %u restore packets\n",total,saves,restores);
}
