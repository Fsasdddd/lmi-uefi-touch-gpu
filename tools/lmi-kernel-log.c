/* Copy bounded kernel diagnostics through the existing console RAM channel.
 * The RAM-only return deliberately omits the native peripheral cleanup and
 * message-buffer replay. kern.msgbuf gives the capacity; proc_kmsgbuf reads
 * the bytes, as Apple's dmesg does. Both operations are read-only. */
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <time.h>
#include <unistd.h>

/* Each deadline is relative to process start, so console output cannot add
 * another full sleep interval to the next sample. */
static int wait_until(time_t deadline) {
    struct timespec now,delay;
    for(;;) {
        if(clock_gettime(CLOCK_MONOTONIC,&now))return -1;
        if(now.tv_sec>=deadline)return 0;
        delay.tv_sec=deadline-now.tv_sec-1;
        delay.tv_nsec=1000000000L-now.tv_nsec;
        if(delay.tv_nsec==1000000000L){delay.tv_sec++;delay.tv_nsec=0;}
        if(nanosleep(&delay,NULL) && errno!=EINTR)return -1;
    }
}

int main(void) {
    setbuf(stdout,NULL);
    void *library=dlopen("/usr/lib/libproc.dylib",RTLD_NOW);
    int (*read_log)(void *,unsigned)=library?(int (*)(void *,unsigned))dlsym(library,"proc_kmsgbuf"):NULL;
    if(!read_log) {puts("LMI_KERNEL_MSGBUF_FAIL proc_kmsgbuf unavailable");return 1;}
    struct timespec start;
    if(clock_gettime(CLOCK_MONOTONIC,&start))return 1;
    const unsigned deadlines[]={60,110,150};
    for(unsigned sample=0;sample<3;sample++) {
        if(wait_until(start.tv_sec+deadlines[sample]))return 1;
        int capacity=0;size_t length=sizeof(capacity);
        if(sysctlbyname("kern.msgbuf",&capacity,&length,NULL,0) || length!=sizeof(capacity) || capacity<=0 || capacity>262144) {
            printf("LMI_KERNEL_MSGBUF_FAIL sample=%u capacity=%d errno=%d\n",sample,capacity,errno);
            continue;
        }
        char *data=malloc((size_t)capacity+1);
        if(!data) return 1;
        int got=read_log(data,(unsigned)capacity);
        if(got<=0 || got>capacity) {
            printf("LMI_KERNEL_MSGBUF_FAIL sample=%u errno=%d\n",sample,errno);
            free(data);continue;
        }
        size_t size=(size_t)got;
        data[size]=0;
        char output[16384];
        printf("LMI_KERNEL_MSGBUF_BEGIN sample=%u bytes=%zu filtered=2\n",sample,size);
        size_t at=0,kept=0;
        while(at<size) {
            size_t end=at;
            while(end<size && data[end]!='\n')end++;
            char saved=data[end];data[end]=0;
            int framebuffer=strstr(data+at,"MiniIOMobileFramebuffer:") &&
                (strstr(data+at," frames in ") || strstr(data+at,"from one frame") ||
                 strstr(data+at,"display "));
            int wanted=strstr(data+at,"ustacks:") || strstr(data+at,"top:") ||
                framebuffer || strstr(data+at,"usertrap:") ||
                strstr(data+at,"userabort:");
            data[end]=saved;
            size_t length=end-at+(end<size);
            if(wanted && kept+length<=sizeof(output)) {
                memcpy(output+kept,data+at,length);
                kept+=length;
            }
            at=end+(end<size);
        }
        size_t sent=0;
        while(sent<kept) {
            ssize_t n=write(1,output+sent,kept-sent);
            if(n<0 && errno==EINTR)continue;
            if(n<=0)break;
            sent+=(size_t)n;
        }
        printf("\nLMI_KERNEL_MSGBUF_END sample=%u scanned=%zu written=%zu\n",sample,at,sent);
        free(data);
    }
    return 0;
}
