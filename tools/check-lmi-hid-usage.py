"""Exercise the actual usage recheck decision with native accessors stubbed.

This verifies scope and rejection, not iOS initialization or phone interaction.
"""
from pathlib import Path
import hashlib, json, subprocess

repo = Path(__file__).resolve().parents[1]
source = repo / 'userland-source/userland/src/inject.c'
text = source.read_text()
body = text.split('static void\ninput_usage_initial_properties(', 1)[1]
body = 'static void\ninput_usage_initial_properties(' + body.split('\nstatic void\ninput_usage_install', 1)[0]
out = repo / 'out/lmi-hid-usage-host'
out.mkdir(exist_ok=True)
prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
typedef const void *id, *CFTypeRef, *CFNumberRef;
typedef const char *SEL, *CFStringRef;
#define CFSTR(x) (x)
#define kCFNumberIntType 1
#define HID_PAGE_DIGITIZER 13
#define HID_USAGE_TOUCH_SCREEN 4
static unsigned scenario, forwards, reads, writes, cached_page, cached_usage;
static int page, usage;
static id receiver = (id)0x650;
static void original(id self, SEL cmd) {
    assert(self == receiver && !strcmp(cmd, "init"));
    assert(reads == 0 && writes == 0); forwards++;
}
static void (*input_usage_original)(id, SEL) = original;
static unsigned input_usage_cached(id self, const char *key) {
    assert(self == receiver && forwards == 1); reads++;
    return !strcmp(key,"primaryUsagePage") ? cached_page : cached_usage;
}
static id input_usage_property(id self, CFStringRef key) {
    assert(self == receiver && forwards == 1); reads++;
    if(!strcmp(key,"Product")) return scenario == 3 ? "other" : scenario == 4 ? NULL : "Redwood touch screen";
    if(!strcmp(key,"Manufacturer")) return scenario == 5 ? "other" : scenario == 14 ? NULL : "redwood";
    if(!strcmp(key,"PrimaryUsagePage")) return scenario == 6 ? NULL : &page;
    assert(!strcmp(key,"PrimaryUsage")); return scenario == 7 ? NULL : &usage;
}
static bool CFEqual(CFTypeRef a, CFTypeRef b) {return !strcmp(a,b);}
static int CFGetTypeID(CFTypeRef p) {return (scenario==8 && p==&page) || (scenario==9 && p==&usage) ? 2 : 1;}
static int CFNumberGetTypeID(void) {return 1;}
static bool CFNumberGetValue(CFNumberRef p,int type,int *value) {
    assert(type==1); *value=*(const int *)p;
    return !(scenario==10 && p==&page) && !(scenario==11 && p==&usage);
}
static void input_usage_set(id self, const char *key,unsigned value) {
    assert(self==receiver && scenario==0 && forwards==1);
    if(!strcmp(key,"setPrimaryUsagePage:")) {assert(cached_page==0 && value==13);cached_page=value;}
    else {assert(!strcmp(key,"setPrimaryUsage:") && cached_usage==0 && value==4);cached_usage=value;}
    writes++;
}
#define say(...) ((void)0)
'''
suffix = r'''
int main(void) {
    const unsigned pages[] = {0,13,12}, usages[] = {0,4,1};
    unsigned cases=0, repaired=0;
    for(unsigned pi=0;pi<3;pi++) for(unsigned ui=0;ui<3;ui++) {
        for(scenario=0;scenario<15;scenario++) {
            if(scenario==1 || scenario==2) continue;
            forwards=reads=writes=0;
            unsigned before_page=pages[pi], before_usage=usages[ui];
            cached_page=before_page; cached_usage=before_usage;
            page=scenario==12?12:13; usage=scenario==13?1:4;
            bool complete=before_page==13 && before_usage==4;
            bool conflict=before_page==12 || before_usage==1;
            bool repair=scenario==0 && !complete && !conflict;
            input_usage_initial_properties(receiver,"init");
            unsigned expected=repair ? (before_page==0)+(before_usage==0) : 0;
            assert(forwards==1 && writes==expected);
            assert(cached_page==(repair?13:before_page));
            assert(cached_usage==(repair?4:before_usage));
            if(complete || conflict) assert(reads==2);
            repaired+=repair; cases++;
        }
    }
    assert(cases==117 && repaired==3);
    puts("PASS: 117 cases; restore 0/0, 13/0, 0/4; preserve complete/conflicting caches and reject invalid native properties");
}
'''
(out / 'check.c').write_text(prefix + body + suffix)
subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined',
                str(out/'check.c'),'-o',str(out/'check')],check=True)
subprocess.run([str(out/'check')],check=True)
report = dict(result='PASS', scenarios=117, cache_states=9,
              repaired_cache_states=['0/0','13/0','0/4'], invalid_native_controls=12,
              source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),hardware_verified=False)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
