"""Run the actual make_service retry loop with a deterministic HID server.

CF dictionary construction is stubbed; creation/open callbacks, virtual time,
cleanup and the real retry control flow are exercised under ASan/UBSan.
"""
from pathlib import Path
import hashlib,json,subprocess

r=Path(__file__).resolve().parents[1]
source=r/'userland-source/userland/src/inject.c'
s=source.read_text()
a=s.index('static IOHIDServiceClientRef\nmake_service(')
b=s.index('/* One frame of the touch screen:',a)
function=s[a:b]
out=r/'out/lmi-hid-startup-host';out.mkdir(exist_ok=True)
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
typedef void *IOHIDServiceClientRef, *IOHIDEventSystemClientRef;
typedef void *CFMutableDictionaryRef, *CFStringRef, *CFNumberRef, *CFArrayRef;
struct service { void *properties; volatile bool opened; };
static unsigned creates, removes, fails, never_open;
static unsigned long long elapsed;
static void *allocation;
static void *allocate(size_t n,size_t z) { assert(!allocation); return allocation=calloc(n,z); }
static IOHIDServiceClientRef create(struct service *made) {
    creates++;
    if(creates<=fails)return NULL;
    made->opened=!never_open;
    return (void *)(uintptr_t)creates;
}
#define calloc(n,z) allocate(n,z)
#define CFDictionaryCreateMutable(...) ((void *)1)
#define CFStringCreateWithCString(...) ((void *)1)
#define CFArrayCreate(...) ((void *)1)
#define CFDictionarySetValue(...) ((void)0)
#define CFSTR(s) (s)
#define number(n) ((void *)1)
#define IOHIDVirtualServiceClientCreateWithCallbacks(c,p,b,t,m) create(m)
#define IOHIDVirtualServiceClientRemove(s) (++removes)
#define CFRelease(s) ((void)0)
#define usleep(n) (elapsed+=(n))
#define say(...) ((void)0)
'''
suffix=r'''
int main(void) {
    for(unsigned scenario=0;scenario<4;scenario++) {
        creates=removes=elapsed=0;fails=scenario==1?3:scenario==2?100:0;
        never_open=scenario==3;
        void *service=make_service(NULL,"screen",13,4,true);
#ifdef LMI_HID_SIMPLE_RETRY
        const unsigned expected_creates[]={1,4,20,20};
        const unsigned long long expected_time[]={0,750000,4750000,40000000};
        assert(creates==expected_creates[scenario] && elapsed==expected_time[scenario]);
        assert((service!=NULL)==(scenario<2));
#else
        const unsigned expected_creates[]={1,1,1,20};
        assert(creates==expected_creates[scenario]);
        assert((service!=NULL)==(scenario==0));
#endif
        assert(removes==(scenario==3?20:0));
        free(allocation);allocation=NULL;
    }
    return 0;
}
'''
(out/'check.c').write_text(prefix+function+suffix)
for mode,flags in [('retry',['-DLMI_HID_SIMPLE_RETRY=1']),('legacy',[])]:
    executable=out/mode
    subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined',*flags,str(out/'check.c'),'-o',str(executable)],check=True)
    subprocess.run([str(executable)],check=True)
report=dict(result='PASS',retry_scenarios=4,legacy_controls=4,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),hardware_verified=False)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
