/* Real userland GLES rasterization/readback probe. Software renderers fail.
 * Exact red/green triangle over blue, excluding the 64 edge-rule tie pixels.
 * CPU code only checks glReadPixels output and never constructs drawn pixels. */
#include <OpenGLES/ES2/gl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct osmesa_context *OSMesaContext;
extern OSMesaContext OSMesaCreateContextAttribs(const int *,OSMesaContext);
extern unsigned char OSMesaMakeCurrent(OSMesaContext,void *,unsigned,int,int);
static unsigned char window[16*16*4],readback[128+64*64*4+128];
static unsigned shader(unsigned kind,const char *src) {
    unsigned s=glCreateShader(kind);int good;
    glShaderSource(s,1,&src,NULL);glCompileShader(s);glGetShaderiv(s,GL_COMPILE_STATUS,&good);
    if(!good) {char log[1024];glGetShaderInfoLog(s,sizeof(log),NULL,log);printf("LMI_GL_FAIL shader %s\n",log);exit(1);}
    return s;
}
int main(void) {
    setbuf(stdout,NULL);
    const int attr[]={0x22,GL_RGBA,0x33,0x38,0x36,2,0};
    OSMesaContext c=OSMesaCreateContextAttribs(attr,NULL);
    if(!c || !OSMesaMakeCurrent(c,window,GL_UNSIGNED_BYTE,16,16)) {puts("LMI_GL_FAIL context");return 1;}
    const char *renderer=(const char *)glGetString(GL_RENDERER);
    printf("LMI_GL_RENDERER %s\n",renderer?renderer:"missing");
    if(!renderer || !strstr(renderer,"FD650")) {puts("LMI_GL_FAIL hardware renderer required");return 1;}
    unsigned texture,fb;glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,64,64,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
    glGenFramebuffers(1,&fb);glBindFramebuffer(GL_FRAMEBUFFER,fb);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
    if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE) {puts("LMI_GL_FAIL framebuffer");return 1;}
    unsigned p=glCreateProgram();
    glAttachShader(p,shader(GL_VERTEX_SHADER,"attribute vec2 pos;void main(){gl_Position=vec4(pos,0.,1.);}"));
    glAttachShader(p,shader(GL_FRAGMENT_SHADER,"precision mediump float;uniform vec4 colour;void main(){gl_FragColor=colour;}"));
    glBindAttribLocation(p,0,"pos");glLinkProgram(p);int good;glGetProgramiv(p,GL_LINK_STATUS,&good);
    if(!good) {puts("LMI_GL_FAIL link");return 1;}
    const float vertices[]={-1,-1,1,-1,-1,1};
    glUseProgram(p);glViewport(0,0,64,64);glDisable(GL_DITHER);
    glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,0,vertices);glEnableVertexAttribArray(0);
    for(unsigned frame=0;frame<8;frame++) {
        glClearColor(0,0,1,1);glClear(GL_COLOR_BUFFER_BIT);
        glUniform4f(glGetUniformLocation(p,"colour"),!(frame&1),frame&1,0,1);
        glDrawArrays(GL_TRIANGLES,0,3);glFinish();
        memset(readback,0x55,sizeof(readback));glReadPixels(0,0,64,64,GL_RGBA,GL_UNSIGNED_BYTE,readback+128);
        unsigned bad=0,checked=0;
        for(unsigned y=0;y<64;y++)for(unsigned x=0;x<64;x++) {
            if(x+y==63)continue;
            unsigned inside=x+y<63;const unsigned char *v=readback+128+4*(64*y+x);
            unsigned char expected[]={inside && !(frame&1)?255:0,inside && (frame&1)?255:0,inside?0:255,255};
            bad+=memcmp(v,expected,4)!=0;checked++;
        }
        for(unsigned i=0;i<128;i++)bad+=readback[i]!=0x55 || readback[sizeof(readback)-128+i]!=0x55;
        unsigned error=glGetError();printf("LMI_GL_FRAME %u checked=%u bad=%u error=%x\n",frame,checked,bad,error);
        if(bad || error) {puts("LMI_GL_FAIL pixels");return 1;}
    }
    puts("LMI_GL_PASS 8 hardware shader frames, 4032 exact RGBA pixels per frame, both CPU readback guards");
    return 0;
}
