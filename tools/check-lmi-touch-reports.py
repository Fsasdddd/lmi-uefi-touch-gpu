"""Exercise the actual FT3518 decoder block with recorded-format frames in ASan/UBSan."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / 'tools/lmi-touch.c').read_text()
decoder = source.split('            int valid=1;\n', 1)[1].split('            active=next; pause_us(20000);', 1)[0]
scale = source.split('static u32 scale(', 1)[1].split('\n', 1)[0]
unit = r'''
#include <assert.h>
#include <string.h>
#include <stdio.h>
typedef unsigned int u32;
typedef unsigned char u8;
static u32 active, x[10], y[10], bad, reports;
struct event {u32 type,finger,x,y;};
static struct event events[40];
static unsigned count;
static void touch_post(u32 type,u32 finger,u32 px,u32 py) {
    assert(count<40);events[count++]=(struct event){type,finger,px,py};
}
#define field(label,value) ((void)(value))
static void pause_us(u32 us) {(void)us;}
static u32 scale(''' + scale + r'''
static void decode(u8 data[63]) {
    for(int once=0;once<1;once++) {
        u32 next=0;int valid=1;
''' + decoder + r'''
        active=next;
    }
}
static void frame(u8 data[63],unsigned contacts) {
    memset(data,0xff,63);data[2]=contacts;
}
static void slot(u8 data[63],unsigned n,unsigned id,unsigned phase,unsigned px,unsigned py) {
    unsigned at=3+6*n;
    data[at]=(phase<<6)|(px>>8);data[at+1]=px;
    data[at+2]=(id<<4)|(py>>8);data[at+3]=py;
}
static void reset(void) {active=count=bad=reports=0;memset(x,0,sizeof(x));memset(y,0,sizeof(y));}
int main(void) {
    u8 data[63];reset();
    frame(data,1);slot(data,0,0,0,100,500);decode(data);
    assert(active==1 && count==1 && events[0].type==1);
    frame(data,1);slot(data,0,0,2,400,500);decode(data);
    assert(count==2 && events[1].type==2 && events[1].x==scale(400,1079));
    frame(data,0);slot(data,0,0,1,900,500);decode(data);
    assert(!active && count==3 && events[2].type==3 && events[2].x==scale(900,1079));
    /* Count-zero release with zero-filled unused slots cannot create contacts. */
    reset();frame(data,1);slot(data,0,0,0,100,500);decode(data);
    memset(data,0,63);slot(data,0,0,1,950,500);decode(data);
    assert(!active && count==2 && events[1].type==3 && events[1].x==scale(950,1079));
    /* If no explicit up is present, still release once using the last position. */
    reset();frame(data,1);slot(data,0,0,0,123,456);decode(data);
    memset(data,0,63);decode(data);decode(data);
    assert(!active && count==2 && events[1].type==3 && events[1].x==scale(123,1079));
    /* Release one finger while retaining a different finger in the same report. */
    reset();frame(data,2);slot(data,0,2,0,100,200);slot(data,1,5,0,300,400);decode(data);
    frame(data,1);slot(data,0,2,1,800,200);slot(data,1,5,2,350,400);decode(data);
    assert(active==(1u<<5) && count==4 && events[2].type==2 && events[3].type==3);
    assert(events[3].finger==2 && events[3].x==scale(800,1079));
    /* Duplicate live IDs reject the entire frame before emitting or changing coordinates. */
    unsigned previous=count;u32 old=x[5];
    frame(data,2);slot(data,0,5,2,500,400);slot(data,1,5,2,800,400);decode(data);
    assert(count==previous && x[5]==old && active==(1u<<5));
    puts("PASS: actual FT3518 decoder: down/move/final-up coordinates, zero padding, fallback release, multitouch, duplicate rejection");
}
'''
with tempfile.TemporaryDirectory(prefix='lmi-touch-reports-') as directory:
    path = Path(directory)
    (path/'check.c').write_text(unit)
    subprocess.run(['clang', '-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    '-Wall', '-Wextra', '-Werror', str(path/'check.c'), '-o', str(path/'check')], check=True)
    subprocess.run([str(path/'check')], check=True)
