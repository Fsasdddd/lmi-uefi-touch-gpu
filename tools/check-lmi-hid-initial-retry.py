"""Run the actual initialization retry logic against controlled native accessors.

Checks ownership scope, partial caches, recovery, conflicting data, and retry bounds.
Does not claim to emulate Apple's initialization or validate phone interaction.
"""
from pathlib import Path
import hashlib, json, subprocess

repo = Path(__file__).resolve().parents[1]
source = repo / 'userland-source/userland/src/inject.c'
text = source.read_text()
body = text.split('#ifdef LMI_HID_INITIAL_RETRY\n', 1)[1]
body = body.split('\nstatic void\ninput_usage_install', 1)[0]
# Retain the matching preprocessor guard around the first helper section.
body = '#ifdef LMI_HID_INITIAL_RETRY\n' + body
out = repo / 'out/lmi-hid-initial-retry-host'
out.mkdir(exist_ok=True)
prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
typedef const void *id, *CFTypeRef, *CFNumberRef, *CFBooleanRef;
typedef const char *SEL, *CFStringRef;
#define CFSTR(x) (x)
#define kCFNumberIntType 1
#define HID_PAGE_DIGITIZER 13
#define HID_USAGE_TOUCH_SCREEN 4
#define LMI_HID_INITIAL_RETRY 1
#define say(...) ((void)0)
static unsigned forwards, scenario, recover, cached_page, cached_usage;
static bool cached_built;
static const int raw_page=13, raw_usage=4, wrong_page=12, wrong_usage=1;
static const bool yes=true, no=false;
static id receiver=(id)0x650;
static void original(id self, SEL cmd) {
    assert(self==receiver && !strcmp(cmd,"init"));
    forwards++;
    if(forwards>1 && recover && forwards==recover+1) {
        cached_page=scenario==24?12:13; cached_usage=4; cached_built=true;
    }
}
static void (*input_usage_original)(id,SEL)=original;
static unsigned input_usage_cached(id self,const char *key) {
    assert(self==receiver && forwards>=1);
    if(!strcmp(key,"primaryUsagePage"))return cached_page;
    assert(!strcmp(key,"primaryUsage"));return cached_usage;
}
static SEL sel_registerName(const char *s) {return s;}
static bool objc_msgSend(id self,SEL cmd) {
    assert(self==receiver && !strcmp(cmd,"isBuiltIn"));return cached_built;
}
static id input_usage_property(id self,CFStringRef key) {
    assert(self==receiver && forwards>=1);
    if(scenario==23 && forwards>=2)return NULL;
    if(!strcmp(key,"Product"))return scenario==1?NULL:scenario==2?"other":scenario==3?(id)&yes:"Redwood touch screen";
    if(!strcmp(key,"Manufacturer"))return scenario==4?NULL:scenario==5?"other":scenario==6?(id)&yes:"redwood";
    if(!strcmp(key,"Transport"))return scenario==7?NULL:scenario==8?"USB":scenario==9?(id)&yes:"SPI";
    if(!strcmp(key,"PrimaryUsagePage"))return scenario==10?NULL:scenario==11?(id)&yes:scenario==12?&wrong_page:&raw_page;
    if(!strcmp(key,"PrimaryUsage"))return scenario==13?NULL:scenario==14?(id)&yes:scenario==15?&wrong_usage:&raw_usage;
    if(!strcmp(key,"Built-In"))return scenario==16?NULL:scenario==17?(id)&raw_page:scenario==18?&no:&yes;
    assert(!strcmp(key,"DisplayIntegrated"));return scenario==19?NULL:scenario==20?(id)&raw_page:scenario==21?&no:&yes;
}
static int CFGetTypeID(CFTypeRef p) {
    if(p==&yes || p==&no)return 3;
    if(p==&raw_page || p==&raw_usage || p==&wrong_page || p==&wrong_usage)return 2;
    return 1;
}
static int CFStringGetTypeID(void){return 1;}
static int CFNumberGetTypeID(void){return 2;}
static int CFBooleanGetTypeID(void){return 3;}
static bool CFEqual(CFTypeRef a,CFTypeRef b){return !strcmp(a,b);}
static bool CFBooleanGetValue(CFBooleanRef p){assert(CFGetTypeID(p)==3);return *(const bool *)p;}
static bool CFNumberGetValue(CFNumberRef p,int type,int *value){
    assert(type==1 && CFGetTypeID(p)==2);*value=*(const int *)p;return scenario!=22;
}
'''
suffix = r'''
int main(void) {
    unsigned cases=0,replayed=0,refused=0;
    const unsigned pages[]={0,13,12}, usages[]={0,4,1};
    for(unsigned pi=0;pi<3;pi++)for(unsigned ui=0;ui<3;ui++)for(unsigned bi=0;bi<2;bi++)
    for(scenario=0;scenario<25;scenario++)for(recover=0;recover<3;recover++) {
        unsigned page=pages[pi],usage=usages[ui];
        cached_page=page;cached_usage=usage;cached_built=bi;forwards=0;
        bool conflict=page==12 || usage==1;
        bool complete=page==13 && usage==4 && bi;
        bool allowed=!conflict && !complete && (scenario==0 || scenario==23 || scenario==24);
        unsigned expected=1;
        if(allowed) expected+=scenario==23 || recover==1 ? 1 : 2;
        input_usage_initial_properties(receiver,"init");
        assert(forwards==expected && forwards<=3);
        if(!allowed || !recover || (scenario==23 && recover==2)) {
            assert(cached_page==page && cached_usage==usage && cached_built==bi);
        } else {
            assert(cached_page==(scenario==24?12:13) && cached_usage==4 && cached_built);
        }
        cases++;replayed+=forwards>1;refused+=!allowed;
    }
    assert(cases==1350);
    printf("PASS: %u cases, %u replayed, %u refused; at most 3 native calls; no manual setters\n",cases,replayed,refused);
}
'''
(out/'check.c').write_text(prefix+body+suffix)
subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined',str(out/'check.c'),'-o',str(out/'check')],check=True)
subprocess.run([str(out/'check')],check=True)
report=dict(result='PASS',scenarios=1350,max_native_calls=3,manual_setters=False,
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),hardware_verified=False)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
