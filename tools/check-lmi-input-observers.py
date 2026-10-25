"""Check the actual UIKit observers forward every original event unchanged.

The host supplies Objective-C metadata and HID events. This verifies ABI refusal,
the bounded log, and forwarding under ASan/UBSan, not runtime iOS delivery.
"""
from pathlib import Path
import hashlib,json,subprocess

r=Path(__file__).resolve().parents[1]
source=r/'userland-source/userland/src/inject_sb.c'
s=source.read_text()
body=s[s.index('typedef struct __IOHIDEvent *LMIHIDEventRef;'):]
body=body.split('\n#endif',1)[0]
out=r/'out/lmi-input-observers-host';out.mkdir(exist_ok=True)
prefix=r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef void *id;
typedef const char *SEL;
typedef void (*IMP)(void);
typedef void *Class;
struct method {IMP imp; const char *ret,*arg; unsigned count;};
typedef struct method *Method;
struct __IOHIDEvent {uint32_t type;uint64_t time,sender;};
static struct method methods[2];
static unsigned log_count,forwarded[2],scenario;
static void *expected_self;
static struct __IOHIDEvent *expected_event;
static struct {uint32_t numer,denom;} timebase={625,12};
static uint64_t now_us(void) {return 1000000;}
static void say(const char *fmt,...) {
    if(strncmp(fmt,"LMI_UIKIT_INPUT stage=",22)==0)log_count++;
}
static Class objc_getClass(const char *name) {(void)name;return scenario==5?NULL:(Class)1;}
static SEL sel_registerName(const char *name) {return name;}
static Method class_getInstanceMethod(Class cls,SEL sel) {
    (void)cls;if(scenario==4)return NULL;
    return &methods[strcmp(sel,"_enqueueHIDEvent:")!=0];
}
static char *method_copyReturnType(Method m) {return strdup(m->ret);}
static char *method_copyArgumentType(Method m,unsigned i) {assert(i==2);return strdup(m->arg);}
static unsigned method_getNumberOfArguments(Method m) {return m->count;}
static IMP method_getImplementation(Method m) {return m->imp;}
static IMP method_setImplementation(Method m,IMP imp) {IMP old=m->imp;m->imp=imp;return old;}
uint32_t IOHIDEventGetType(struct __IOHIDEvent *e) {return e->type;}
uint64_t IOHIDEventGetTimeStamp(struct __IOHIDEvent *e) {return e->time;}
uint64_t IOHIDEventGetSenderID(struct __IOHIDEvent *e) {return e->sender;}
static void original0(id self,SEL sel,struct __IOHIDEvent *event) {
    assert(self==expected_self && !strcmp(sel,"_enqueueHIDEvent:") && event==expected_event);forwarded[0]++;
}
static void original1(id self,SEL sel,struct __IOHIDEvent *event) {
    assert(self==expected_self && !strcmp(sel,"_handleHIDEvent:") && event==expected_event);forwarded[1]++;
}
'''
suffix=r'''
int main(void) {
    for(scenario=0;scenario<6;scenario++) {
        methods[0]=(struct method){(IMP)original0,"v","^{__IOHIDEvent=}",3};
        methods[1]=(struct method){(IMP)original1,"v","^{__IOHIDEvent=}",3};
        for(unsigned i=0;i<2;i++) {
            if(scenario==1)methods[i].ret="i";
            if(scenario==2)methods[i].arg="@";
            if(scenario==3)methods[i].count=2;
        }
        input_uikit_watch();
        assert((methods[0].imp==(IMP)input_enqueue)==(scenario==0));
        assert((methods[1].imp==(IMP)input_handle)==(scenario==0));
        if(scenario)continue;
        expected_self=(void *)(uintptr_t)0x1234;
        for(unsigned n=0;n<207;n++) {
            struct __IOHIDEvent event={n==205?3:11,123456+n,650};
            struct __IOHIDEvent before=event;
            expected_event=n==206?NULL:&event;
            ((void (*)(id,SEL,LMIHIDEventRef))methods[0].imp)(expected_self,"_enqueueHIDEvent:",expected_event);
            ((void (*)(id,SEL,LMIHIDEventRef))methods[1].imp)(expected_self,"_handleHIDEvent:",expected_event);
            assert(!memcmp(&event,&before,sizeof(event)));
        }
        assert(forwarded[0]==207 && forwarded[1]==207);
        assert(input_enqueue_count==205 && input_handle_count==205);
        assert(log_count==384);
    }
    puts("PASS: UIKit ABI refusal, 414 unchanged event forwards including NULL/non-digitizer/over-limit, 384 bounded logs");
}
'''
(out/'check.c').write_text(prefix+body+suffix)
subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'check.c'),'-o',str(out/'check')],check=True)
subprocess.run([str(out/'check')],check=True)
report=dict(result='PASS',abi_scenarios=6,unchanged_forwards=414,bounded_logs=384,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),hardware_verified=False)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
