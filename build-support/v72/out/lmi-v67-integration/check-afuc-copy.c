/* Execute the unmodified Mesa emulator against this device's actual SQE.
 * This validates firmware semantics only, never hardware bandwidth or DMA. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "emu.h"
#include "util.h"

static void test(uint32_t *fw, unsigned words, unsigned count)
{
   struct emu e = {.instrs = fw + 1, .sizedwords = words - 1,
                   .fw_id = afuc_get_fwid(fw[1]), .quiet = true, .run_mode = true};
   emu_init(&e);
   unsigned table = e.instrs[1] & 0xffff;
   assert(table + 128 <= e.sizedwords);
   unsigned handler = e.instrs[table + 0x75];
   assert(handler == 0xd3d);
   const uint64_t src = 0x2000000, dst = 0x4000000;
   uint32_t *s = e.gpumem + src, *d = e.gpumem + dst;
   for (unsigned i = 0; i < count + 16; i++) {
      s[i] = (i * 0x13579bdu) ^ 0xa1b2c3d4u;
      d[i] = 0xdeadbeef;
   }
   uint32_t args[] = {count, src, src >> 32, dst, dst >> 32};
   for (unsigned i = 0; i < 5; i++) assert(emu_queue_push(&e.roq, args[i]));
   emu_set_gpr_reg(&e, REG_REM, 5);
   e.gpr_regs.pc = handler;
   unsigned steps = 0;
   while (!e.waitin && steps < 100) {emu_step(&e); steps++;}
   assert(e.waitin && !e.roq.count && !emu_get_gpr_reg(&e, REG_REM));
   assert(!memcmp(s, d, count * 4));
   for (unsigned i = count; i < count + 16; i++) assert(d[i] == 0xdeadbeef);
   printf("PASS firmware CP_MEMCPY count=%u bytes=%u handler=%x steps=%u guard=16\n",
          count, count * 4, handler, steps);
   emu_fini(&e);
}
int main(int argc, char **argv)
{
   assert(argc == 2);
   FILE *f = fopen(argv[1], "rb"); assert(f);
   assert(!fseek(f, 0, SEEK_END)); long bytes = ftell(f); rewind(f);
   assert(bytes == 31632);
   uint32_t *fw = malloc(bytes); assert(fw && fread(fw, 1, bytes, f) == (size_t)bytes); fclose(f);
   assert(!afuc_util_init(afuc_get_fwid(fw[1]), &gpuver, false));
   unsigned counts[] = {255, 1136, 65535, 65536, 4544u * 2436u / 4};
   for (unsigned i = 0; i < sizeof(counts) / sizeof(counts[0]); i++) test(fw, bytes / 4, counts[i]);
   free(fw);
   return 0;
}
