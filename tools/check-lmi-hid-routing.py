"""Exercise actual bounded BackBoard wrappers under ASan/UBSan.

Verify forwarding, pointer outputs, return values, log bounds and installation
refusal. This does not claim that private methods are reached on the phone.
"""
from pathlib import Path
import hashlib, json, subprocess

repo = Path(__file__).resolve().parents[1]
source = repo / 'userland-source/userland/src/inject.c'
text = source.read_text()
body = text.split('#ifdef LMI_HID_ROUTING_TRACE\n/* Bounded observation', 1)[1]
body = '/* Bounded observation' + body.split('\n#endif', 1)[0]
out = repo / 'out/lmi-hid-routing-host'
out.mkdir(exist_ok=True)
prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef void *id;
typedef const char *SEL;
typedef void (*IMP)(void);
typedef void *Class;
struct method { IMP imp; const char *encoding; };
typedef struct method *Method;
struct event { uint32_t type; uint64_t timestamp; };
typedef struct event *IOHIDEventRef;
typedef const void *CFTypeRef;
typedef const char *CFStringRef;
#define kCFStringEncodingUTF8 0
static CFStringRef CFCopyDescription(CFTypeRef object) {(void)object;return "observed state";}
static bool CFStringGetCString(CFStringRef value,char *buffer,size_t length,int encoding) {
    (void)encoding;snprintf(buffer,length,"%s",value);return true;
}
static void CFRelease(CFStringRef value) {(void)value;}
static struct method method;
static unsigned scenario, installs, logs, forwards;
static uint32_t instruction = 0xd10243ffU;
static id wanted_self=(void *)1, wanted_sender=(void *)2, wanted_dispatcher=(void *)3;
static IOHIDEventRef wanted_event, replacement;
static IOHIDEventRef *wanted_pointer;
static bool *wanted_touchpad;
static Class objc_getClass(const char *name) {(void)name;return scenario==1?NULL:(Class)1;}
static SEL sel_registerName(const char *name) {return name;}
static Method class_getInstanceMethod(Class cls,SEL sel) {(void)cls;(void)sel;return scenario==2?NULL:&method;}
static IMP method_getImplementation(Method m) {return m->imp;}
static const char *method_getTypeEncoding(Method m) {return m->encoding;}
static IMP method_setImplementation(Method m,IMP next) {IMP old=m->imp;m->imp=next;installs++;return old;}
static const char *object_getClassName(id object) {assert(object==wanted_sender);return "sender";}
static uint32_t IOHIDEventGetType(IOHIDEventRef e) {return e->type;}
static uint64_t IOHIDEventGetTimeStamp(IOHIDEventRef e) {return e->timestamp;}
static uint64_t micros(uint64_t t) {return t;}
static uint32_t _dyld_image_count(void) {return 0;}
static const char *_dyld_get_image_name(uint32_t i) {(void)i;return NULL;}
static const void *_dyld_get_image_header(uint32_t i) {(void)i;return NULL;}
static void say(const char *format,...) {
    if(!strncmp(format,"LMI_BK_PROCESS n=",17)||!strncmp(format,"LMI_BK_SERVICE n=",17)) logs++;
}
static long original_process(id self,SEL cmd,IOHIDEventRef *event,id sender,id dispatcher) {
    assert(self==wanted_self && !strcmp(cmd,"process"));
    assert(event==wanted_pointer && sender==wanted_sender && dispatcher==wanted_dispatcher);
    if(event) {assert(*event==wanted_event);*event=replacement;}
    forwards++;return -650;
}
static id original_service(id self,SEL cmd,IOHIDEventRef event,id sender,bool *touchpad) {
    assert(self==wanted_self && !strcmp(cmd,"service") && event==wanted_event && sender==wanted_sender);
    assert(touchpad==wanted_touchpad);if(touchpad)*touchpad=true;
    forwards++;return (id)0x650;
}
static id original_state(id self,SEL cmd,id service) {
    assert(self==wanted_self && !strcmp(cmd,"state") && service==wanted_sender);
    forwards++;return (id)0x123;
}
'''
suffix = r'''
int main(void) {
    for(scenario=0;scenario<6;scenario++) {
        method=(struct method){(IMP)&instruction,scenario==3?"wrong":"test"};
        unsigned before=installs;
        IMP result=routing_replace("test","test",(uintptr_t)&instruction+(scenario==4?4:0),
            scenario==5?0:instruction,(IMP)routing_process);
        assert((result!=NULL)==(scenario==0));
        assert(installs-before==(scenario==0));
    }
    routing_process_original=original_process;routing_service_original=original_service;
    routing_state_original=original_state;
    for(unsigned n=0;n<70;n++) {
        struct event event={n==65?3:11,1000+n}, other={11,2000+n}, before=event;
        wanted_event=(n==66||n==67)?NULL:&event;
        replacement=&other;
        IOHIDEventRef pointer=wanted_event;
        wanted_pointer=n==67?NULL:&pointer;
        wanted_sender=n==68?NULL:(id)2;
        bool touchpad=false;
        wanted_touchpad=n==69?NULL:&touchpad;
        assert(routing_process(wanted_self,"process",wanted_pointer,wanted_sender,wanted_dispatcher)==-650);
        assert(wanted_pointer==NULL||pointer==replacement);
        assert(routing_service(wanted_self,"service",wanted_event,wanted_sender,wanted_touchpad)==(id)0x650);
        assert(wanted_touchpad==NULL||touchpad);
        assert(routing_state(wanted_self,"state",wanted_sender)==(id)0x123);
        assert(!memcmp(&event,&before,sizeof(event)));
    }
    assert(forwards==210 && logs==64 && routing_state_count==70);
    assert(routing_process_count==67 && routing_service_count==67);
    puts("PASS: 5 refusal controls; 210 unchanged forwards and return/output values; bounded records");
}
'''
(out/'check.c').write_text(prefix+body+suffix)
subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',
                str(out/'check.c'),'-o',str(out/'check')],check=True)
subprocess.run([str(out/'check')],check=True)
report=dict(result='PASS',refusal_controls=5,unchanged_forwards=210,bounded_logs=64,
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),hardware_verified=False)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
