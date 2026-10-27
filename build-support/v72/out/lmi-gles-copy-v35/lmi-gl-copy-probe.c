/* Run the frozen production target_to_surface functions on actual FD650 GLES.
 * Source pixels are test inputs. Results come only from GPU blit/readback.
 * The generated include contains the original and corrected function bodies. */
#include <CoreFoundation/CoreFoundation.h>
#include <IOSurface/IOSurfaceRef.h>
#include <OpenGLES/ES3/gl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "redwood_gl.h"
#ifndef GL_BGRA
#define GL_BGRA 0x80e1
#endif

struct image {
    GLuint texture, mirror;
    IOSurfaceRef surface;
    bool invert, drawn, shared;
    GLsizei width, height;
};
struct eagl { GLuint reader, writer, framebuffer; };
#include "copy-production.inc"

enum { W=32, H=24, GUARD=64 };
static uint8_t pixels[W*H*4], output[GUARD+W*H*4+GUARD];

static IOSurfaceRef make_surface(void) {
    CFMutableDictionaryRef props=CFDictionaryCreateMutable(NULL,0,
        &kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    const CFStringRef keys[]={kIOSurfaceWidth,kIOSurfaceHeight,
        kIOSurfaceBytesPerElement,kIOSurfacePixelFormat};
    const int values[]={W,H,4,0x42475241};
    for(unsigned i=0;i<4;i++) {
        CFNumberRef n=CFNumberCreate(NULL,kCFNumberIntType,&values[i]);
        CFDictionarySetValue(props,keys[i],n);CFRelease(n);
    }
    IOSurfaceRef s=IOSurfaceCreate(props);CFRelease(props);return s;
}

static unsigned compare(bool invert) {
    unsigned bad=0;
    for(unsigned y=0;y<H;y++) for(unsigned x=0;x<W;x++) {
        unsigned from=((invert?H-1-y:y)*W+x)*4;
        bad+=memcmp(output+GUARD+(y*W+x)*4,pixels+from,4)!=0;
    }
    return bad;
}

int main(void) {
    setbuf(stdout,NULL);
    struct redwood_gl *gl=redwood_gl_create(3);
    if(!gl || !redwood_gl_make_current(gl)) {puts("LMI_GL_COPY_FAIL context");return 1;}
    const char *renderer=(const char *)glGetString(GL_RENDERER);
    printf("LMI_GL_COPY_RENDERER %s\n",renderer?renderer:"missing");
    if(!renderer || !strstr(renderer,"FD650") || strstr(renderer,"softpipe") || strstr(renderer,"llvmpipe")) {
        puts("LMI_GL_COPY_FAIL hardware");return 1;
    }
    IOSurfaceRef surface=make_surface();
    if(!surface) {puts("LMI_GL_COPY_FAIL surface");return 1;}
    GLuint texture[2],fb[2];glGenTextures(2,texture);glGenFramebuffers(2,fb);
    for(unsigned i=0;i<2;i++) {
        glBindTexture(GL_TEXTURE_2D,texture[i]);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
        if(i==0) glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,W,H,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
        else if(!redwood_gl_surface_texture(gl,IOSurfaceGetID(surface))) {
            puts("LMI_GL_COPY_FAIL shared mirror");return 1;
        }
        glBindFramebuffer(GL_FRAMEBUFFER,fb[i]);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture[i],0);
        if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE) {
            puts("LMI_GL_COPY_FAIL framebuffer");return 1;
        }
    }
    glDisable(GL_DITHER);glDisable(GL_BLEND);
    const GLint boxes[4][4]={{0,0,W,H},{3,4,7,5},{0,0,0,0},{W+5,H+5,2,2}};
    struct eagl context={0};
    for(unsigned c=0;c<8;c++) {
        bool inverted=(c&1)!=0, clipped=c/2!=0;
        const GLint *box=boxes[c/2];
        for(unsigned y=0;y<H;y++) for(unsigned x=0;x<W;x++) {
            uint8_t *p=pixels+4*(y*W+x);
            p[0]=1+x*3+c;p[1]=2+y*5;p[2]=3+(x^y);p[3]=255;
        }
        glBindTexture(GL_TEXTURE_2D,texture[0]);
        glTexSubImage2D(GL_TEXTURE_2D,0,0,0,W,H,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
        struct image image={.texture=texture[0],.mirror=texture[1],.surface=surface,
            .invert=inverted,.drawn=true,.width=W,.height=H};
        unsigned mismatch[2]={0},state_bad=0,guard_bad=0;
        for(unsigned variant=0;variant<2;variant++) {
            glDisable(GL_SCISSOR_TEST);glBindFramebuffer(GL_FRAMEBUFFER,fb[1]);
            glClearColor(1,0,1,1);glClear(GL_COLOR_BUFFER_BIT);
            glScissor(box[0],box[1],box[2],box[3]);
            if(clipped) glEnable(GL_SCISSOR_TEST);
            glBindFramebuffer(GL_READ_FRAMEBUFFER,fb[0]);
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER,fb[1]);
            image.drawn=true;
            if(variant==0) control_target_to_surface(&context,&image);
            else target_to_surface(&context,&image);
            GLint read,draw,after[4];
            glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&read);
            glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&draw);
            glGetIntegerv(GL_SCISSOR_BOX,after);
            state_bad+=read!=(GLint)fb[0] || draw!=(GLint)fb[1] || image.drawn ||
                !!glIsEnabled(GL_SCISSOR_TEST)!=clipped || memcmp(box,after,sizeof(after))!=0;
            glFinish();glBindFramebuffer(GL_READ_FRAMEBUFFER,fb[1]);
            memset(output,0x55,sizeof(output));
            glReadPixels(0,0,W,H,GL_RGBA,GL_UNSIGNED_BYTE,output+GUARD);
            mismatch[variant]=compare(inverted);
            for(unsigned i=0;i<GUARD;i++) guard_bad+=output[i]!=0x55 || output[sizeof(output)-GUARD+i]!=0x55;
        }
        unsigned error=glGetError();
        printf("LMI_GL_COPY_CASE %u checked=%u control_bad=%u fixed_bad=%u state_bad=%u guard_bad=%u error=%x\n",
            c,W*H,mismatch[0],mismatch[1],state_bad,guard_bad,error);
        unsigned expected=c/2==1 ? W*H-35 : c/2>=2 ? W*H : 0;
        if(mismatch[0]!=expected || mismatch[1] || state_bad || guard_bad || error) {
            puts("LMI_GL_COPY_FAIL regression");return 1;
        }
    }
    glDeleteFramebuffers(2,fb);glDeleteFramebuffers(1,&context.reader);glDeleteFramebuffers(1,&context.writer);
    glDeleteTextures(2,texture);CFRelease(surface);redwood_gl_destroy(gl);
    puts("LMI_GL_COPY_PASS 8 cases, real shared IOSurface mirror, old-path negative control, state and readback guards");
    return 0;
}
