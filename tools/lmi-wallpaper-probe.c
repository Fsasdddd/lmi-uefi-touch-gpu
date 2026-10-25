/* Read-only WallpaperKit startup probe. Run as a bounded background RAM job.
 * Stage markers distinguish image decoding, framework loading and collection
 * discovery; a resource conversion alone cannot establish wallpaper rendering. */
#include <dlfcn.h>
#include <CoreFoundation/CoreFoundation.h>
#include <ImageIO/ImageIO.h>
#include <objc/message.h>
#include <objc/runtime.h>
#include <signal.h>
#include <stdio.h>
#include <unistd.h>

static id send(id object,const char *selector) {
    return ((id (*)(id,SEL))objc_msgSend)(object,sel_registerName(selector));
}
static id string(const char *text) {
    return ((id (*)(id,SEL,const char *))objc_msgSend)((id)objc_getClass("NSString"),
        sel_registerName("stringWithUTF8String:"),text);
}
static void timed_out(int signal) {
    (void)signal;
    static const char message[]="LMI_WALLPAPER_TIMEOUT\n";
    write(1,message,sizeof(message)-1);
    _exit(2);
}
int main(int argc,char **argv) {
    setbuf(stdout,NULL);
    signal(SIGALRM,timed_out);alarm(12);
    puts("LMI_WALLPAPER_BEGIN");
    id pool=send(send((id)objc_getClass("NSAutoreleasePool"),"alloc"),"init");
    if(argc>1) {
        puts("LMI_WALLPAPER_IMAGEIO_OPEN_BEGIN");
        CFURLRef url=CFURLCreateFromFileSystemRepresentation(NULL,(const UInt8 *)argv[1],
            __builtin_strlen(argv[1]),false);
        CGImageSourceRef source=url?CGImageSourceCreateWithURL(url,NULL):NULL;
        printf("LMI_WALLPAPER_IMAGEIO_OPEN_RESULT %s\n",source?"source-created":"failed");
        if(source) {
            puts("LMI_WALLPAPER_IMAGEIO_DECODE_BEGIN");
            const void *keys[]={kCGImageSourceShouldCacheImmediately};
            const void *values[]={kCFBooleanTrue};
            CFDictionaryRef options=CFDictionaryCreate(NULL,keys,values,1,
                &kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
            CGImageRef pixels=CGImageSourceCreateImageAtIndex(source,0,options);
            CFDataRef bytes=pixels?CGDataProviderCopyData(CGImageGetDataProvider(pixels)):NULL;
            printf("LMI_WALLPAPER_IMAGEIO_DECODE_RESULT width=%zu height=%zu bytes=%ld\n",
                pixels?CGImageGetWidth(pixels):0,pixels?CGImageGetHeight(pixels):0,
                bytes?(long)CFDataGetLength(bytes):0);
            if(bytes)CFRelease(bytes);
            if(pixels)CGImageRelease(pixels);
            CFRelease(options);CFRelease(source);
        }
        if(url)CFRelease(url);
        puts("LMI_WALLPAPER_UIIMAGE_BEGIN");
        id image=((id (*)(id,SEL,id))objc_msgSend)((id)objc_getClass("UIImage"),
            sel_registerName("imageWithContentsOfFile:"),string(argv[1]));
        printf("LMI_WALLPAPER_UIIMAGE_RESULT %s\n",image?"object-created":"missing-or-failed");
    }
    puts("LMI_WALLPAPER_FRAMEWORK_BEGIN");
    void *framework=dlopen("/System/Library/PrivateFrameworks/WallpaperKit.framework/WallpaperKit",RTLD_NOW);
    if(!framework) {printf("LMI_WALLPAPER_FAIL dlopen %s\n",dlerror());return 1;}
    Class manager=objc_getClass("WKWallpaperRepresentingCollectionsManager");
    if(!manager) {puts("LMI_WALLPAPER_FAIL manager class");return 1;}
    puts("LMI_WALLPAPER_COLLECTIONS_BEGIN");
    id collections=((id (*)(id,SEL,id,BOOL))objc_msgSend)(send((id)manager,"alloc"),
        sel_registerName("initWithDownloadManager:loadLegacyContent:"),nil,NO);
    if(!collections) {puts("LMI_WALLPAPER_FAIL collections init");return 1;}
    long count=((long (*)(id,SEL))objc_msgSend)(collections,sel_registerName("numberOfWallpaperCollections"));
    printf("LMI_WALLPAPER_COLLECTIONS_RESULT %ld\n",count);
    for(long n=0;n<count && n<16;n++) {
        id collection=((id (*)(id,SEL,long))objc_msgSend)(collections,sel_registerName("wallpaperCollectionAtIndex:"),n);
        id description=send(collection,"description");
        const char *text=(const char *)send(description,"UTF8String");
        printf("LMI_WALLPAPER_COLLECTION %ld %s\n",n,text?text:"missing description");
    }
    alarm(0);
    puts("LMI_WALLPAPER_DONE");
    send(pool,"drain");
    return 0;
}
