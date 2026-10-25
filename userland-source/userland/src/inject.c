/*
 * libredwood.dylib: code of ours inside stock iOS programs.
 *
 * launchd starts the jobs named in INJECT (see build.sh / mkjobs.py) with
 * DYLD_INSERT_LIBRARIES pointing here; dyld honours that because the kernel's AMFI stand-in
 * says so. What is done depends on the program:
 *
 *   backboardd   the window server (CoreAnimation in QuartzCore). There is no GPU, so the
 *                render server must use CoreAnimation's own software rasterizer, and we want to
 *                see why a frame is or is not drawn. The C++ objects are reached by replacing
 *                entries of their virtual tables.
 *                It is also where input enters the system: backboardd is the HID event server,
 *                and without Apple's multitouch driver it has no touch screen. We give it one:
 *                a "virtual" HID service that turns the samples of /dev/redwood-touch into the
 *                events that driver would have sent.
 *
 *                And it does not wait five seconds for an ambient light sensor.
 *
 *   containermanagerd (both of them)
 *                They ask the user manager for the "personas" of the user, of which this
 *                system has none, twenty times a second apart before they give up -- and
 *                everything that needs a container (the window server, for one) waits with
 *                them. Told that personas are not supported, they do not ask.
 *
 * Addresses of things inside the dyld shared cache are those of iOS 16.5 (20F66) for iPhone10,3;
 * every one is checked against what is expected to be there before it is touched.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <dispatch/dispatch.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <mach/mach.h>
#include <mach/mach_time.h>
#ifdef LMI_HID_ROUTING_TRACE
#include <mach-o/dyld.h>
#endif
#include <notify.h>
#include <objc/message.h>
#include <objc/runtime.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <signal.h>
#include <sys/ucontext.h>
#include <unistd.h>

#include "redwood_gl.h"
#include "redwood_input.h"

extern const void *_dyld_get_shared_cache_range(size_t *length);

#define CACHE_BASE 0x180000000UL                /* where the cache was built to be, before the slide */
#define REDWOOD_GL "/redwood/lib/libredwood-gl.dylib"

static uintptr_t slide;

static void
say(const char *format, ...)
{
	char line[256];
	va_list ap;
	int n;

	va_start(ap, format);
	n = vsnprintf(line, sizeof(line), format, ap);
	va_end(ap);
	if (n > (int)sizeof(line) - 1) {
		n = sizeof(line) - 1;
	}
	write(2, line, (size_t)n);
}

/* Replace one entry of a virtual table (unslid address `slot`) that must now hold `expected`. */
static void *
replace_virtual(const char *what, uintptr_t slot, uintptr_t expected, void *replacement)
{
	uintptr_t *entry = (uintptr_t *)(slot + slide);
	vm_address_t page = (vm_address_t)entry & ~(vm_address_t)(vm_page_size - 1);
	kern_return_t kr;
	void *original;

	if (*entry != expected + slide) {
		say("redwood: %s: found %#lx, expected %#lx; left alone\n", what, *entry - slide, expected);
		return NULL;
	}
	/* the tables are in read-only memory shared by every process: get a private writable copy of the page */
	kr = vm_protect(mach_task_self(), page, vm_page_size, FALSE, VM_PROT_READ | VM_PROT_WRITE | VM_PROT_COPY);
	if (kr != KERN_SUCCESS) {
		say("redwood: %s: cannot make the table writable (%d)\n", what, kr);
		return NULL;
	}
	original = (void *)*entry;
	*entry = (uintptr_t)replacement;
	vm_protect(mach_task_self(), page, vm_page_size, FALSE, VM_PROT_READ);
	return original;
}

/* ---- backboardd: CA::WindowServer ------------------------------------------------------------ */

#define VT_APPLE_CLCD_DISPLAY   0x1d5b44520UL   /* vtable for CA::WindowServer::AppleCLCDDisplay */
#define VT_EAGL_SERVER          0x1d5b45c58UL   /* vtable for CA::WindowServer::EAGLServer */
#define VSLOT(vtable, offset)   ((vtable) + 0x10 + (offset))

#define DISPLAY_FLAGS(display)  (*(uint64_t *)((char *)(display) + 0x9f2))
#define DISPLAY_B233(display)   (*(uint8_t *)((char *)(display) + 0x233))

static int (*orig_is_ready)(void *display);
static int (*orig_ignore_update_p)(void *display, void *update);
static uintptr_t (*orig_begin_update)(void *display, void *update);
static uintptr_t (*orig_finish_update)(void *display, void *update, unsigned flags);
static void *(*orig_renderer)(void *server);
static uintptr_t (*orig_render_update)(void *server, void *update, unsigned *flags);

static unsigned calls_ready, calls_ignore, calls_begin, calls_finish, calls_render;
static int last_ready = -1, last_ignore = -1;

static int
my_is_ready(void *display)
{
	int ready = orig_is_ready(display);

	if (ready != last_ready || calls_ready < 3) {
		say("redwood: is_ready -> %d (call %u, flags %#llx, b233 %#x)\n", ready, calls_ready,
		    (unsigned long long)DISPLAY_FLAGS(display), DISPLAY_B233(display));
		last_ready = ready;
	}
	calls_ready++;
	return ready;
}

static int
my_ignore_update_p(void *display, void *update)
{
	int ignore = orig_ignore_update_p(display, update) & 1;

	if (ignore != last_ignore || calls_ignore < 3) {
		uint64_t *q = (uint64_t *)((char *)display + 0x220);

		say("redwood: ignore_update_p -> %d (call %u, flags %#llx, update flags %#x)\n", ignore, calls_ignore,
		    (unsigned long long)DISPLAY_FLAGS(display), *(uint32_t *)((char *)update + 0xf0));
		say("redwood:   display +0x220: %#llx %#llx %#llx %#llx %#llx %#llx\n", (unsigned long long)q[0],
		    (unsigned long long)q[1], (unsigned long long)q[2], (unsigned long long)q[3], (unsigned long long)q[4],
		    (unsigned long long)q[5]);
		last_ignore = ignore;
	}
	calls_ignore++;
	return ignore;
}

static uintptr_t
my_begin_update(void *display, void *update)
{
	uintptr_t r = orig_begin_update(display, update);

	if (calls_begin++ < 6) {
		say("redwood: begin_update -> %#lx (flags %#llx)\n", r, (unsigned long long)DISPLAY_FLAGS(display));
	}
	return r;
}

static uintptr_t
my_finish_update(void *display, void *update, unsigned flags)
{
	uintptr_t r = orig_finish_update(display, update, flags);

	if (calls_finish++ < 6) {
		say("redwood: finish_update(%#x) -> %#lx\n", flags, r);
	}
	return r;
}

/*
 * Every frame the server asks for its renderer, and while there is none it tries again to make a
 * Metal and then an OpenGL ES context, which costs a lot and cannot succeed here. One try is enough:
 * without a renderer the server draws with CA::WindowServer::Server::sw_renderer().
 */
static void *
my_renderer(void *server)
{
	static int failed, said;
	void *renderer;

	if (failed) {
		return NULL;
	}
	renderer = orig_renderer(server);
	if (renderer == NULL) {
		failed = 1;
		say("redwood: no accelerated renderer; the software one will draw\n");
	} else if (!said) {
		said = 1;
		say("redwood: the server has an accelerated renderer (%p)\n", renderer);
	}
	return renderer;
}

static uintptr_t
my_render_update(void *server, void *update, unsigned *flags)
{
	uintptr_t r = orig_render_update(server, update, flags);

	if (calls_render++ < 6) {
		say("redwood: render_update -> %#lx (flags %#x)\n", r, flags ? *flags : 0);
	}
	return r;
}

/*
 * CoreAnimation draws a layer's pixels with one of ninety "functions" (a fragment shader each: an
 * image as it is, an image through a colour matrix, a blur of so many samples, ...), and asks
 * its renderer which of them it has. Its OpenGL ES renderer has not half of them (the Metal one
 * has all). Which ones are asked for and missing is worth knowing: said once each.
 * (The last of the ninety, "cst", is not asked about: the OpenGL ES renderer draws it with no
 * program at all. The lock screen's wallpaper goes that way; see plain_draw_begin() in eagl.c.)
 */
#define VT_GLES_CONTEXT         0x1d5b3b540UL   /* vtable for CA::OGL::GLESContext */

static int gl_loaded;                           /* CoreAnimation draws with OpenGL ES (opengl_es() below) */
static void (*gl_function_refused)(unsigned function);  /* our OpenGL ES library keeps count (eagl.c, the census) */
static int (*orig_function_supported)(void *context);

/*
 * Boot-arg glyes=N[,N...]: the renderer is made to answer that it has those functions after all.
 * It has no shader for them, so CoreAnimation draws them with no program -- which is the way the
 * functions it never asks about are drawn, and which our OpenGL ES library stands in for
 * (eagl.c, plain_draw_begin()); without this, what needs such a function is not drawn at all.
 * For finding out what a missing function is for: with it the draw is made, its numbers arrive
 * (function_uniform below), and the picture says whether the thing was that function's.
 */
/*
 * Saying yes to a function the renderer has no shader for is not enough and not safe. Told yes for
 * "sb3" (40) -- the four samples of a shadow's blur, which our OpenGL ES library has a stand-in for
 * (eagl.c, blur4_fragment) -- CoreAnimation takes the way of one it has a shader for, finds none,
 * and the window server dies; it came back every half a minute, with SpringBoard after it, and the
 * stand-in was never reached: a function it asks about and is told yes to is not one it draws with
 * no program. What is needed is to hand it a program where it looks for one, which is another
 * entry of the same table. Until then it is told the truth, and what needs that function is not
 * drawn -- the shadow under a card of the switcher of running applications.
 */
/*
 * Where the window server died. Its crash reports never arrive here -- the kernel says "Failed to
 * send exception EXC_CORPSE_NOTIFY" and that is the end of it -- so a SIGSEGV in CoreAnimation has
 * been a silent restart every half a minute with nothing to go on. This turns one into a line: the
 * address it touched and where it was, both as they would be in the shared cache as built, which
 * "ipsw dyld a2s" turns into a name. Then the signal is let through to kill the process as before.
 */
static void
say_the_fault(int signal_number, siginfo_t *info, void *context_in)
{
	ucontext_t *context = context_in;
	uintptr_t pc = 0, lr = 0;

	if (context != NULL && context->uc_mcontext != NULL) {
		pc = (uintptr_t)context->uc_mcontext->__ss.__pc;
		lr = (uintptr_t)context->uc_mcontext->__ss.__lr;
	}
	/*
	 * And who called, by walking the frame pointers: on arm64 each frame holds the previous one
	 * at [fp] and its return address at [fp + 8]. The crash itself is usually in a library
	 * function -- strdup of a null name, say -- and the frame that matters is two or three up.
	 */
	char frames[8 * 20 + 1] = "";
	size_t used = 0;
	uintptr_t fp = context != NULL && context->uc_mcontext != NULL ? (uintptr_t)context->uc_mcontext->__ss.__fp : 0;

	for (unsigned i = 0; i < 8 && fp != 0 && (fp & 7) == 0; i++) {
		uintptr_t next = ((uintptr_t *)fp)[0], ret = ((uintptr_t *)fp)[1];

		if (ret == 0) {
			break;
		}
		used += (size_t)snprintf(frames + used, sizeof(frames) - used, " %#lx", ret - slide);
		fp = next > fp ? next : 0;      /* the chain only ever goes up the stack */
	}
	say("redwood: signal %d at %p, pc %#lx, lr %#lx, called from%s (unslid)\n", signal_number,
	    info != NULL ? info->si_addr : NULL, pc - slide, lr - slide, frames);
	signal(signal_number, SIG_DFL);
	raise(signal_number);
}

static void
watch_for_faults(void)
{
	struct sigaction action;

	memset(&action, 0, sizeof(action));
	action.sa_sigaction = say_the_fault;
	action.sa_flags = SA_SIGINFO | SA_RESETHAND;
	sigaction(SIGSEGV, &action, NULL);
	sigaction(SIGBUS, &action, NULL);
	/* An Objective-C exception that nobody catches ends in abort(), not in a fault, and a program
	   that dies that way says nothing at all here -- a run that restarted a daemon 31 times was
	   silent until these three were watched as well. */
	sigaction(SIGABRT, &action, NULL);
	sigaction(SIGILL, &action, NULL);
	sigaction(SIGTRAP, &action, NULL);
}

/*
 * CoreAnimation's OpenGL ES renderer keeps the source of one fragment shader per function in a
 * table of its own -- unslid 0x1d5b54790, indexed by the function's number -- and the functions it
 * has no shader for are null entries there. That is the whole of "the renderer has no function
 * 40": GLContext::create_shader takes the source from that table, and function_supported answers
 * from the same place. Made to answer yes without the entry, create_shader hands the null to
 * strdup and the window server dies in strlen, which is what glyes=40 did for a whole afternoon.
 *
 * So the way to give the renderer a function is to give it a source. "sb3" (40) is the single
 * pass of a blur -- GaussianBlurFilter::render -> Context::blur_surface ->
 * BlurState::single_pass_blur -- the one that lays the shadow under a card of the switcher of
 * running applications. It is given the same four places as "ds4" (26) and has no weights of its
 * own, so this is ds4's own shader with the weights taken out, in the dialect the others are
 * written in (sampler2DRect, varying, gl_FragData -- the preamble is added by the renderer).
 *
 * Where this stands. With the entry filled the window server no longer dies: thirty-odd crashes a
 * run become none, with glyes=40 as well, and the function really is drawn -- the renderer rewrites
 * our source into its own dialect (sampler2DRect becomes sampler2D) and compiles it, and the
 * picture changes by a level or two across the whole screen where before it did not change at all.
 *
 * What it does not do is bring back a shadow, and the reason is that none was missing. This
 * function was taken up because a note here said the shadow under a card of the switcher was not
 * drawn; that note was reasoning from "the function is refused", not an observation. Against the
 * same frame drawn by CoreAnimation's software renderer -- which draws everything correctly, only
 * slowly -- the edge of a card is the same to the level: 18, 17, 17, then the card. There is no
 * soft falloff there in either, so there is nothing of that kind to restore.
 *
 * Its effect is nil for a second reason worth writing down: the four places reach the shader as
 * varyings that a vertex shader computes from "uniform highp vec2 offset[4]", and the two groups
 * of four numbers function_uniform delivers for it are of the order of 5e-19 -- zero, for a
 * blur. CoreAnimation asks for the single-pass blur exactly when the radius is too small to need
 * the multi-pass one, so the four samples coincide and the pass copies what it was given.
 */
#define CA_SHADER_TABLE         0x1d5b54790UL

static const char shadow_blur_source[] =
    "uniform lowp sampler2DRect texture0;\n"
    "varying highp vec2 texcoord0, texcoord1, texcoord2, texcoord3;\n"
    "void main () {\n"
    "  lowp vec4 q0, q1, q2, q3;\n"
    "  q0 = texture2DRect(texture0, texcoord0);\n"
    "  q1 = texture2DRect(texture0, texcoord1);\n"
    "  q2 = texture2DRect(texture0, texcoord2);\n"
    "  q3 = texture2DRect(texture0, texcoord3);\n"
    "  gl_FragData[0] = (q0 + q1 + q2 + q3) * 0.25;\n"
    "}\n";

static void
give_the_renderer_a_shader(unsigned function, const char *source)
{
	uintptr_t *entry = (uintptr_t *)(CA_SHADER_TABLE + slide + 8 * (uintptr_t)function);
	vm_address_t page = (vm_address_t)entry & ~(vm_address_t)(vm_page_size - 1);

	if (*entry != 0) {
		say("redwood: CoreAnimation's function %u has a shader of its own; left alone\n", function);
		return;
	}
	/* the table is read-only memory shared by every process: a private writable copy of the page */
	if (vm_protect(mach_task_self(), page, vm_page_size, FALSE,
	    VM_PROT_READ | VM_PROT_WRITE | VM_PROT_COPY) != KERN_SUCCESS) {
		say("redwood: CoreAnimation's function %u: cannot make the table of shaders writable\n", function);
		return;
	}
	*entry = (uintptr_t)source;
	vm_protect(mach_task_self(), page, vm_page_size, FALSE, VM_PROT_READ);
	say("redwood: CoreAnimation's function %u (\"sb3\") is given a shader of ours\n", function);
}

static uint8_t say_yes[90];
static int compile_shaders_said;                /* boot-arg glcompile=1: write down every shader source */

static void
functions_said_yes(const char *arguments)
{
	static const char names[] = REDWOOD_CA_FUNCTIONS;
	const char *argument = strstr(arguments, "glno=");

	/* glno=N[,N...]: and the other way about, for seeing what a function of ours stands in for */
	for (argument = argument != NULL ? argument + 5 : NULL; argument != NULL && *argument >= '0' && *argument <= '9';) {
		unsigned function = (unsigned)strtoul(argument, (char **)&argument, 10);

		if (function < 90) {
			say_yes[function] = 0;
			say("redwood: the renderer will not answer that it has CoreAnimation's function %u (\"%.3s\")\n",
			    function, names + 4 * function);
		}
		argument = *argument == ',' ? argument + 1 : NULL;
	}
	argument = strstr(arguments, "glyes=");
	for (argument = argument != NULL ? argument + 6 : NULL; argument != NULL && *argument >= '0' && *argument <= '9';) {
		unsigned function = (unsigned)strtoul(argument, (char **)&argument, 10);

		if (function < 90) {
			say_yes[function] = 1;
			say("redwood: the renderer will answer that it has CoreAnimation's function %u (\"%.3s\")\n",
			    function, names + 4 * function);
		}
		argument = *argument == ',' ? argument + 1 : NULL;
	}
}

/*
 * CA::OGL::Context::compile_shader(const char *) -- slot 0x060 of the same table. The OpenGL ES
 * renderer does not carry its shaders ready-made: it assembles the text of each from a preamble
 * (GLESContext::shader_preamble, slot 0x400) and pieces chosen by what the draw needs, and
 * compiles it here. That makes this the place where it looks for a program, and therefore the
 * place where one can be handed to it for a function it has no pieces for ("sb3", 40: the four
 * samples of a shadow's blur, missing under the cards of the switcher). This writes down what it
 * is asked to compile, so that a run with glyes=40 says whether a source is assembled at all
 * before the window server dies, and what it looks like if so.
 */
static uintptr_t (*orig_compile_shader)(void *context, const char *source);

static uintptr_t
my_compile_shader(void *context, const char *source)
{
	static unsigned told, seen;

	/* that it is called at all is worth one line, because a renderer that compiles nothing here
	   would mean the text is assembled and compiled somewhere this table does not reach */
	if (seen++ == 0) {
		say("redwood: CoreAnimation compiles its shaders through the table (the first of them, %zu characters)\n",
		    source != NULL ? strlen(source) : 0);
	}
	if (compile_shaders_said && told < 24) {
		told++;
		say("redwood: CoreAnimation compiles a shader, %zu characters:\n", source != NULL ? strlen(source) : 0);
		for (size_t at = 0, length = source != NULL ? strlen(source) : 0; at < length; at += 700) {
			say("redwood:  %.700s\n", source + at);
		}
	}
	return orig_compile_shader(context, source);
}

static int
my_function_supported(void *context)
{
	static const char names[] = REDWOOD_CA_FUNCTIONS;
	static uint8_t said[256];
	int supported = orig_function_supported(context);
	uint8_t function = *(*(uint8_t **)((char *)context + 0x10) + 0x10);

	if (!supported && function < 90 && say_yes[function] && gl_loaded) {
		if (!said[function]) {
			said[function] = 1;
			say("redwood: CoreAnimation's function %u (\"%.3s\"): the renderer is made to say it has it\n",
			    function, names + 4 * function);
		}
		return 1;
	}
	if (!supported && gl_function_refused != NULL) {
		gl_function_refused(function);
	}
	if (!supported && !said[function]) {
		said[function] = 1;
		say("redwood: CoreAnimation's OpenGL ES renderer has no function %u (\"%.3s\"): what needs it is not drawn\n",
		    function, function < 90 ? names + 4 * function : "?");
	}
	return supported;
}

/*
 * A function that takes numbers besides its textures (a colour matrix, say) is given them through
 * GLContext::function_uniform(), which hands them to the function's shader. The functions the
 * OpenGL ES renderer has no shader for are drawn all the same, with no program, and their numbers
 * go nowhere. Our OpenGL ES library draws some of those with programs of its own (eagl.c,
 * plain_draw_begin()): it is told the numbers here, and with them the context, in which it
 * finds which function a draw is.
 */
static void (*orig_function_uniform)(void *context, unsigned index, size_t components, size_t count, const float *values);
static void (*gl_function_values)(void *context, unsigned function, unsigned index, size_t components, size_t count,
    const float *values);

static void
my_function_uniform(void *context, unsigned index, size_t components, size_t count, const float *values)
{
	uint8_t function = *(*(uint8_t **)((char *)context + 0x10) + 0x10);

	/*
	 * Who is calling. Told yes for a function it has no shader for (glyes=40), CoreAnimation gets
	 * this far -- it hands the function its numbers -- and then dies in whatever comes next, which
	 * is where it takes the program for the function out of a table of its own. These addresses,
	 * unslid, name that caller for "ipsw dyld a2s", and it is the only thread to pull: nothing is
	 * ever compiled for the function (no shader arrives at our library), and the compiler is not
	 * reached through the renderer's table either.
	 */
	if (say_yes[function < 90 ? function : 0]) {
		static uint8_t told[90];

		if (function < 90 && !told[function]) {
			told[function] = 1;
			say("redwood: function %u takes its numbers from %#lx %#lx %#lx\n", function,
			    (uintptr_t)__builtin_return_address(0) - slide,
			    (uintptr_t)__builtin_return_address(1) - slide,
			    (uintptr_t)__builtin_return_address(2) - slide);
		}
	}
	if (gl_function_values != NULL) {
		gl_function_values(context, function, index, components, count, values);
	}
	orig_function_uniform(context, index, components, count, values);
}

/* ---- backboardd: the window server stays on OpenGL ES ------------------------------------------ */

/*
 * With the Metal properties on the accelerator service (boot-arg metal=1) MTLCreateSystemDefaultDevice()
 * answers in every process, and the window server is the first to ask. Its road to Metal has no fork
 * in it: CA::WindowServer::EAGLServer's constructor (0x1883d1544) calls renderer() (0x1882e2548) with a
 * direct branch -- past the virtual table, so my_renderer() above never sees that first call -- and
 * renderer() calls CAMetalContextCreate() (0x18837b718), which is nothing but a dispatch_once around
 * MTLCreateSystemDefaultDevice(). A device that is not nil goes straight into
 * CA::OGL::new_metal_context() (0x18847efcc), where the renderer asks for its shaders:
 *
 *	quartzcore_bundle = [NSBundle bundleWithIdentifier:@"com.apple.QuartzCore"];
 *	assert(quartzcore_bundle != nil);				ogl-metal.mm:3305
 *	metallib_url = [quartzcore_bundle URLForResource:@"default" withExtension:@"metallib"];
 *	assert(metallib_url != nil);					ogl-metal.mm:3308 -- here
 *
 * The bundle is found; the resource is not, because QuartzCore.framework/default.metallib is not in
 * this image (ios165/select-system.py drops every .metallib under the framework directories). That is
 * fourteen aborts in one boot with launchd restarting the server after each -- logs/135751-run.log --
 * and the window server is the one process that must not crash-loop: nothing is drawn at all while it
 * is down. The road that works here is the other one: renderer() falls back to
 * [EAGLContext initWithAPI:3] and CA::OGL::GLESContext when the device is nil, and behind EAGLContext
 * is our own OpenGL ES (userland/src/eagl.c, Mesa off-screen).
 *
 * So the device is taken out of this process before CoreAnimation can ask for it. Metal keeps every
 * device it has made in one static NSMutableArray, and MTLCreateSystemDefaultDevice() is no more than
 * "if that array holds exactly one object, return it" (its block, 0x181a3442c): an empty array answers
 * nil without a single instruction of Metal's being touched. The array is built on first use, so it
 * has to be asked for first -- and that creates the device object, which is exactly what
 * CoreAnimation's next instruction would have done anyway, so it costs this process nothing it was not
 * already paying. The device is retained and never released on purpose: what our driver's -dealloc
 * would do to a GPU this same process is drawing on through Mesa is not measured.
 *
 * Boot-arg camtl=1 leaves the device where it is, for the boot that means to put CoreAnimation on the
 * Metal road deliberately -- which needs QuartzCore's default.metallib in the image first, or this
 * same assertion comes back.
 */
#define MTL_DEVICE_ARRAY        0x1e1efe9a0UL   /* Metal's static NSMutableArray *_deviceArray */
#define CA_DETECT_DISPLAYS      0x1884da264UL   /* -[CAWindowServer _detectDisplays] */

extern id objc_retain(id object);

static void (*orig_detect_displays)(id server, SEL selector);

static void
keep_metal_from_core_animation(void)
{
	unsigned long (*ask)(id, SEL) = (unsigned long (*)(id, SEL))objc_msgSend;
	void (*tell)(id, SEL) = (void (*)(id, SEL))objc_msgSend;
	id (*create)(void) = (id (*)(void))dlsym(RTLD_DEFAULT, "MTLCreateSystemDefaultDevice");
	id *slot = (id *)(MTL_DEVICE_ARRAY + slide);
	id device, array;
	unsigned long held;

	if (create == NULL) {
		say("redwood: metal: this process has no MTLCreateSystemDefaultDevice; nothing to keep\n");
		return;
	}
	if ((device = create()) == NULL) {
		say("redwood: metal: no device in this process; CoreAnimation keeps OpenGL ES by itself\n");
		return;
	}
	if ((array = *slot) == NULL) {
		say("redwood: metal: a device, but nothing at %#lx; the device list is NOT emptied\n",
		    MTL_DEVICE_ARRAY);
		return;
	}
	if (!((BOOL (*)(id, SEL, Class))objc_msgSend)(array, sel_registerName("isKindOfClass:"),
	    objc_getClass("NSMutableArray"))) {
		say("redwood: metal: %#lx holds a %s, not Metal's device array; left alone\n", MTL_DEVICE_ARRAY,
		    object_getClassName(array));
		return;
	}
	held = ask(array, sel_registerName("count"));
	objc_retain(device);
	tell(array, sel_registerName("removeAllObjects"));
	say("redwood: metal: %s taken out of the window server (%lu in the list, %lu now); "
	    "MTLCreateSystemDefaultDevice() = %s\n", object_getClassName(device), held,
	    ask(array, sel_registerName("count")), create() != NULL ? "A DEVICE STILL" : "nil");
}

/*
 * -[CAWindowServer _detectDisplays] is the caller of CA::WindowServer::AppleDisplay::new_server(),
 * which builds the EAGLServer whose constructor asks for the device: the last Objective-C method on
 * the way in, and the only hook on this path that does not mean writing to Apple's code.
 */
static void
my_detect_displays(id server, SEL selector)
{
	static int once;

	if (!once) {
		once = 1;
		keep_metal_from_core_animation();
	}
	orig_detect_displays(server, selector);
}

static void
window_server_keeps_opengl_es(void)
{
	char arguments[1024] = "";
	size_t size = sizeof(arguments) - 1;
	Class cls;
	Method method;
	IMP original;

	if (sysctlbyname("kern.bootargs", arguments, &size, NULL, 0) == 0 && strstr(arguments, "camtl=1") != NULL) {
		say("redwood: camtl=1: CoreAnimation may have the Metal device (it needs "
		    "QuartzCore.framework/default.metallib in the image)\n");
		return;
	}
	cls = objc_getClass("CAWindowServer");
	method = cls ? class_getInstanceMethod(cls, sel_registerName("_detectDisplays")) : NULL;
	original = method ? method_getImplementation(method) : NULL;
	if (original == NULL || (uintptr_t)original != CA_DETECT_DISPLAYS + slide) {
		say("redwood: -[CAWindowServer _detectDisplays]: found %#lx, not what was expected; left alone, "
		    "and CoreAnimation may take the Metal road\n", original ? (uintptr_t)original - slide : 0);
		return;
	}
	orig_detect_displays = (void (*)(id, SEL))original;
	method_setImplementation(method, (IMP)my_detect_displays);
}

static void
window_server_fixes(void)
{
	window_server_keeps_opengl_es();
	orig_is_ready = replace_virtual("is_ready", VSLOT(VT_APPLE_CLCD_DISPLAY, 0xb0), 0x1882f0908UL, my_is_ready);
	orig_ignore_update_p = replace_virtual("ignore_update_p", VSLOT(VT_APPLE_CLCD_DISPLAY, 0x138), 0x1882e0c90UL,
	    my_ignore_update_p);
	orig_begin_update = replace_virtual("begin_update", VSLOT(VT_APPLE_CLCD_DISPLAY, 0x170), 0x1882ddda4UL,
	    my_begin_update);
	orig_finish_update = replace_virtual("finish_update", VSLOT(VT_APPLE_CLCD_DISPLAY, 0x178), 0x1882c8568UL,
	    my_finish_update);
	orig_renderer = replace_virtual("renderer", VSLOT(VT_EAGL_SERVER, 0x1a0), 0x1882e2548UL, my_renderer);
	orig_render_update = replace_virtual("render_update", VSLOT(VT_EAGL_SERVER, 0x178), 0x18835770cUL,
	    my_render_update);
	if (gl_loaded) {
		orig_function_supported = replace_virtual("function_supported", VSLOT(VT_GLES_CONTEXT, 0x378), 0x1884a9308UL,
		    my_function_supported);
		if (gl_function_values != NULL) {
			orig_function_uniform = replace_virtual("function_uniform", VSLOT(VT_GLES_CONTEXT, 0x388), 0x1884a9350UL,
			    my_function_uniform);
		}
		/* always, because the boot-args are read in another place than this and the order of the
		   two is not ours to rely on; the hook writes nothing unless glcompile=1 */
		orig_compile_shader = (uintptr_t (*)(void *, const char *))replace_virtual("compile_shader",
		    VSLOT(VT_GLES_CONTEXT, 0x060), 0x1883fc808UL, my_compile_shader);
		say("redwood: the shader compiler of CoreAnimation is %s\n", orig_compile_shader ? "watched" : "NOT watched");
		watch_for_faults();
		{
			char arguments[1024] = "";
			size_t size = sizeof(arguments) - 1;

			if (sysctlbyname("kern.bootargs", arguments, &size, NULL, 0) == 0 &&
			    strstr(arguments, "glsb3=1") != NULL) {
				give_the_renderer_a_shader(40, shadow_blur_source);
			}
		}
	}
	say("redwood: window server hooks %s\n", orig_is_ready && orig_ignore_update_p && orig_begin_update &&
	    orig_finish_update && orig_renderer && orig_render_update ? "installed" : "INCOMPLETE");
}

/* ---- backboardd: no ambient light sensor ------------------------------------------------------------ */

/*
 * CoreBrightness (-[BLControl waitForALSArrival], called while the window server starts) waits
 * five seconds for the ambient light sensor to turn up among the HID services. There is none
 * and none will come: do not wait for that.
 *
 * Wait for something else instead, at this convenient point: our own touch screen service.
 * backboardd takes for its touch screen a service that is there when its touch processing
 * starts, a moment later; one that turns up afterwards it does not notice. (For as long as
 * the five seconds were waited here, ours was always in time by accident.)
 */
static dispatch_semaphore_t input_services_made;

static void
wait_for_als_arrival(__unused id self, __unused SEL selector)
{
	if (input_services_made != NULL &&
	    dispatch_semaphore_wait(input_services_made, dispatch_time(DISPATCH_TIME_NOW, 5 * NSEC_PER_SEC)) != 0) {
		say("redwood: input: no touch screen service after five seconds; going on without\n");
	}
}

__attribute__((unused)) static void
brightness_fixes(void)
{
	Class cls = objc_getClass("BLControl");
	Method method = cls ? class_getInstanceMethod(cls, sel_registerName("waitForALSArrival")) : NULL;
	IMP original = method ? method_getImplementation(method) : NULL;

	if (original == NULL || (uintptr_t)original != 0x1af043734UL + slide) {
		say("redwood: -[BLControl waitForALSArrival]: found %#lx, not what was expected; left alone\n",
		    original ? (uintptr_t)original - slide : 0);
		return;
	}
	method_setImplementation(method, (IMP)wait_for_als_arrival);
}

/* ---- backboardd: the touch screen and the buttons ---------------------------------------------- */

/* IOKit's HID event system, the part that has no public header on iOS (prototypes checked against 20F66) */
typedef struct __IOHIDEvent *IOHIDEventRef;
typedef struct __IOHIDEventSystemClient *IOHIDEventSystemClientRef;
typedef struct __IOHIDServiceClient *IOHIDServiceClientRef;

/* IOHIDVirtualServiceClientCallbacksV2 */
struct virtual_service_callbacks {
	uint64_t version;               /* 2 */
	void (*notification)(void *target, void *refcon, IOHIDServiceClientRef service, uint32_t type, CFDictionaryRef property);
	Boolean (*setProperty)(void *target, void *refcon, IOHIDServiceClientRef service, CFStringRef key, CFTypeRef value);
	CFTypeRef (*copyProperty)(void *target, void *refcon, IOHIDServiceClientRef service, CFStringRef key);
	IOHIDEventRef (*copyEvent)(void *target, void *refcon, IOHIDServiceClientRef service, uint32_t type, IOHIDEventRef matching, uint32_t options);
	int (*setOutputEvent)(void *target, void *refcon, IOHIDServiceClientRef service, IOHIDEventRef event);
	CFTypeRef (*copyMatchingEvent)(void *target, void *refcon, IOHIDServiceClientRef service, CFDictionaryRef matching);
};

extern IOHIDEventSystemClientRef IOHIDEventSystemClientCreateWithType(CFAllocatorRef allocator, int type, CFDictionaryRef attributes);
extern void IOHIDEventSystemClientScheduleWithDispatchQueue(IOHIDEventSystemClientRef client, dispatch_queue_t queue);
extern IOHIDServiceClientRef IOHIDVirtualServiceClientCreateWithCallbacks(IOHIDEventSystemClientRef client, CFDictionaryRef attributes,
    const struct virtual_service_callbacks *callbacks, void *target, void *refcon);
extern Boolean IOHIDVirtualServiceClientRemove(IOHIDServiceClientRef service);
extern Boolean IOHIDVirtualServiceClientDispatchEvent(IOHIDServiceClientRef service, IOHIDEventRef event);
extern IOHIDEventRef IOHIDEventCreateDigitizerEvent(CFAllocatorRef allocator, uint64_t time, uint32_t transducer, uint32_t index,
    uint32_t identity, uint32_t event_mask, uint32_t button_mask, double x, double y, double z, double tip_pressure,
    double barrel_pressure, double twist, Boolean range, Boolean touch, uint32_t options);
extern IOHIDEventRef IOHIDEventCreateDigitizerFingerEvent(CFAllocatorRef allocator, uint64_t time, uint32_t index, uint32_t identity,
    uint32_t event_mask, double x, double y, double z, double tip_pressure, double twist, Boolean range, Boolean touch,
    uint32_t options);
extern IOHIDEventRef IOHIDEventCreateKeyboardEvent(CFAllocatorRef allocator, uint64_t time, uint32_t usage_page, uint32_t usage,
    Boolean down, uint32_t options);
extern void IOHIDEventAppendEvent(IOHIDEventRef parent, IOHIDEventRef child, uint32_t options);
extern void IOHIDEventSetIntegerValue(IOHIDEventRef event, uint32_t field, CFIndex value);

#define HID_CLIENT_SIMPLE               4       /* a client that only sends */
#define HID_CLIENT_RATE_CONTROLLED      3       /* what IOHIDEventSystemClientCreate() makes */
#define HID_PAGE_DIGITIZER              0x0d
#define HID_USAGE_TOUCH_SCREEN          0x04
#define HID_PAGE_CONSUMER               0x0c
#define HID_USAGE_CONSUMER_CONTROL      0x01
#define HID_USAGE_POWER                 0x30    /* the lock button */
#define HID_USAGE_MENU                  0x40    /* the home button */
#define HID_USAGE_VOLUME_UP             0xe9
#define HID_USAGE_VOLUME_DOWN           0xea
#define DIGITIZER_HAND                  3       /* kIOHIDDigitizerTransducerTypeHand */
#define DIGITIZER_RANGE                 0x1     /* event mask: what has changed */
#define DIGITIZER_TOUCH                 0x2
#define DIGITIZER_POSITION              0x4
#define DIGITIZER_FROM_EDGE_TIP         0x800   /* not a change: this finger came in over an edge of the screen */
#define FIELD_IS_BUILT_IN               0x4
#define FIELD_DIGITIZER_DISPLAY_INTEGRATED 0xb0019

#define MAX_FINGERS     10

/*
 * A finger that lands this close to an edge of the screen (a fraction of the width or the height)
 * is said to have come in over that edge. Apple's touch controller tells that from the shape of
 * the contact and marks the finger's events; UIKit's screen edge recognizers (the swipe up that
 * leaves an application, the swipe back in a navigation stack, the pull down from the top) take
 * no touch that is not so marked, whatever its path. All we have is where the finger landed.
 */
#define EDGE_SIDE       (16.0 / 375)
#define EDGE_TOP        (16.0 / 812)
#define EDGE_BOTTOM     (34.0 / 812)    /* the strip below the applications' content, where the home bar is */

static struct {
	bool touching, edge;
	double x, y;
} fingers[MAX_FINGERS];

static CFNumberRef
number(int value)
{
	return CFNumberCreate(NULL, kCFNumberIntType, &value);
}

/* A service of ours (the callbacks' refcon): what it says of itself, and whether the event server has taken it. */
struct service {
	CFMutableDictionaryRef properties;
	volatile bool opened;
};

/* The properties of a service of ours; the event server asks for them one at a time. */
static CFTypeRef
service_copy_property(__unused void *target, void *refcon, __unused IOHIDServiceClientRef service, CFStringRef key)
{
	static CFMutableSetRef asked;
	CFTypeRef value = CFDictionaryGetValue(((struct service *)refcon)->properties, key);

	if (asked == NULL) {
		asked = CFSetCreateMutable(NULL, 0, &kCFTypeSetCallBacks);
	}
	if (value == NULL && !CFSetContainsValue(asked, key) && CFSetGetCount(asked) < 40) {
		char name[96] = "?";

		CFSetAddValue(asked, key);
		CFStringGetCString(key, name, sizeof(name), kCFStringEncodingUTF8);
		say("redwood: input: the event server asks for property \"%s\", which we do not have\n", name);
	}
	return value ? CFRetain(value) : NULL;
}

/*
 * What the window server last asked of the touch screen ("TouchDetectionMode"), in the low
 * byte: 1 = report touches; TOUCH_MODE_WAKE while the display is off and a tap is to wake it
 * -- which Apple's multitouch controller then does on its own; TOUCH_MODE_OFF = nothing at
 * all. (Seen: 0xff and 0xfe during the boot, 0x1 with the display on, 0x1fe after the lock
 * button.)
 */
#define TOUCH_MODE_WAKE         0xfe
#define TOUCH_MODE_OFF          0xff
static volatile int touch_mode;

/* What the event server tells a service of ours: said once per name, to learn what there is. */
static Boolean
service_set_property(__unused void *target, void *refcon, __unused IOHIDServiceClientRef service, CFStringRef key,
    CFTypeRef value)
{
	static CFMutableSetRef told;
	char name[96] = "?", text[160] = "?";
	CFStringRef description;

	/* the last thing the event server does when it opens a service; see make_service() */
	if (key != NULL && value != NULL && CFEqual(key, CFSTR("DeviceOpenedByEventSystem")) &&
	    CFGetTypeID(value) == CFBooleanGetTypeID() && CFBooleanGetValue(value)) {
		((struct service *)refcon)->opened = true;
	}
	if (key != NULL && value != NULL && CFEqual(key, CFSTR("TouchDetectionMode")) && CFGetTypeID(value) == CFNumberGetTypeID()) {
		int mode = 0;

		CFNumberGetValue(value, kCFNumberIntType, &mode);
		if (mode != touch_mode) {
			say("redwood: input: touch detection mode %#x\n", mode);
		}
		touch_mode = mode;
	}
	if (told == NULL) {
		told = CFSetCreateMutable(NULL, 0, &kCFTypeSetCallBacks);
	}
	if (key != NULL && !CFSetContainsValue(told, key) && CFSetGetCount(told) < 24) {
		CFSetAddValue(told, key);
		CFStringGetCString(key, name, sizeof(name), kCFStringEncodingUTF8);
		description = value ? CFCopyDescription(value) : NULL;
		if (description != NULL) {
			CFStringGetCString(description, text, sizeof(text), kCFStringEncodingUTF8);
			CFRelease(description);
		}
		say("redwood: input: the event server sets \"%s\" = %s\n", name, text);
	}
	return true;
}

static void
service_notification(__unused void *target, __unused void *refcon, __unused IOHIDServiceClientRef service,
    __unused uint32_t type, __unused CFDictionaryRef property)
{
}

static const struct virtual_service_callbacks service_callbacks = {
	.version = 2, .notification = service_notification, .setProperty = service_set_property,
	.copyProperty = service_copy_property,
};

/*
 * A HID service of ours inside the event server: built in, with one usage.
 *
 * The event server is this very program, and it is still starting. A client that reaches it at
 * the wrong moment of that (backboardd's "HID system open ... start": the connection is made
 * and then replaced, "IOHIDEventSystemServer died. Reestablishing connection.") is left with a
 * service the server cannot talk to and never opens -- and a touch screen that backboardd waits
 * for in vain ("still waiting for a main screen digitizer"). When that moment comes depends on
 * how fast the machine is and on how many processors it has, so no fixed delay avoids it:
 * the service is made again until the server has opened it.
 */
static IOHIDServiceClientRef
make_service(IOHIDEventSystemClientRef client, const char *product, int page, int usage, bool display)
{
	struct service *made = calloc(1, sizeof(*made));
	IOHIDServiceClientRef service = NULL;
	CFMutableDictionaryRef properties = CFDictionaryCreateMutable(NULL, 0, &kCFTypeDictionaryKeyCallBacks,
	    &kCFTypeDictionaryValueCallBacks);
	CFMutableDictionaryRef pair = CFDictionaryCreateMutable(NULL, 0, &kCFTypeDictionaryKeyCallBacks,
	    &kCFTypeDictionaryValueCallBacks);
	CFStringRef name = CFStringCreateWithCString(NULL, product, kCFStringEncodingUTF8);
	CFNumberRef page_number = number(page), usage_number = number(usage), zero = number(0);
	CFArrayRef pairs;

	CFDictionarySetValue(pair, CFSTR("DeviceUsagePage"), page_number);
	CFDictionarySetValue(pair, CFSTR("DeviceUsage"), usage_number);
	pairs = CFArrayCreate(NULL, (const void **)&pair, 1, &kCFTypeArrayCallBacks);
	CFDictionarySetValue(properties, CFSTR("PrimaryUsagePage"), page_number);
	CFDictionarySetValue(properties, CFSTR("PrimaryUsage"), usage_number);
	CFDictionarySetValue(properties, CFSTR("DeviceUsagePage"), page_number);
	CFDictionarySetValue(properties, CFSTR("DeviceUsage"), usage_number);
	CFDictionarySetValue(properties, CFSTR("DeviceUsagePairs"), pairs);
	CFDictionarySetValue(properties, CFSTR("Built-In"), kCFBooleanTrue);
	CFDictionarySetValue(properties, CFSTR("Transport"), CFSTR("SPI"));
	CFDictionarySetValue(properties, CFSTR("Manufacturer"), CFSTR("redwood"));
	CFDictionarySetValue(properties, CFSTR("Product"), name);
	CFDictionarySetValue(properties, CFSTR("VendorID"), zero);
	CFDictionarySetValue(properties, CFSTR("ProductID"), zero);
	if (display) {
		CFDictionarySetValue(properties, CFSTR("DisplayIntegrated"), kCFBooleanTrue);
	}
	/* the dictionary stays: it is what service_copy_property() answers from */
	made->properties = properties;
	for (int attempt = 1; attempt <= 20; attempt++) {
		made->opened = false;
		service = IOHIDVirtualServiceClientCreateWithCallbacks(client, properties, &service_callbacks, NULL, made);
		if (service == NULL) {
#ifdef LMI_HID_SIMPLE_RETRY
			/* An SMP boot can reach this before the event server will create
			 * a simple client's service. Keep the supported sending client and
			 * its scheduled connection; let it reconnect before trying again. */
			if (attempt < 20) {
				say("LMI_HID_CREATE_RETRY product=%s attempt=%d\n", product, attempt);
				usleep(250000);
				continue;
			}
#endif
			break;
		}
		for (int tenths = 0; tenths < 20 && !made->opened; tenths++) {
			usleep(100000);
		}
		if (made->opened) {
			break;
		}
		say("redwood: input: the event server has not opened \"%s\" (attempt %d): making it again\n", product, attempt);
		IOHIDVirtualServiceClientRemove(service);
		CFRelease(service);
		service = NULL;
	}
	return service;
}

#ifdef LMI_HID_USAGE_RECHECK
/* The virtual service can already advertise 0xd/4 while BKIOHIDService's
 * initial property reads cached 0/0 (v30). Re-read through the stock serialized
 * property accessor before matching publishes the initialized sender. Never
 * infer a device type from an event or change a nonzero cached usage. */
static void (*input_usage_original)(id, SEL);

static id
input_usage_property(id service, CFStringRef key)
{
	return ((id (*)(id, SEL, id))objc_msgSend)(service, sel_registerName("propertyForKey:"), (id)key);
}

static unsigned
input_usage_cached(id service, const char *selector)
{
	return ((unsigned (*)(id, SEL))objc_msgSend)(service, sel_registerName(selector));
}

static void
input_usage_set(id service, const char *selector, unsigned value)
{
	((void (*)(id, SEL, unsigned))objc_msgSend)(service, sel_registerName(selector), value);
}

static void
input_usage_initial_properties(id self, SEL cmd)
{
	input_usage_original(self, cmd);
	unsigned page = input_usage_cached(self, "primaryUsagePage");
	unsigned usage = input_usage_cached(self, "primaryUsage");
	if (page != 0 || usage != 0) {
		return;
	}
	id product = input_usage_property(self, CFSTR("Product"));
	id maker = input_usage_property(self, CFSTR("Manufacturer"));
	if (!product || !maker || !CFEqual((CFTypeRef)product, CFSTR("Redwood touch screen")) ||
	    !CFEqual((CFTypeRef)maker, CFSTR("redwood"))) {
		return;
	}
	id p = input_usage_property(self, CFSTR("PrimaryUsagePage"));
	id u = input_usage_property(self, CFSTR("PrimaryUsage"));
	int actual_page = 0, actual_usage = 0;
	if (!p || !u || CFGetTypeID((CFTypeRef)p) != CFNumberGetTypeID() ||
	    CFGetTypeID((CFTypeRef)u) != CFNumberGetTypeID() ||
	    !CFNumberGetValue((CFNumberRef)p, kCFNumberIntType, &actual_page) ||
	    !CFNumberGetValue((CFNumberRef)u, kCFNumberIntType, &actual_usage) ||
	    actual_page != HID_PAGE_DIGITIZER || actual_usage != HID_USAGE_TOUCH_SCREEN) {
		say("LMI_HID_USAGE_RECHECK unavailable page=%d usage=%d\n", actual_page, actual_usage);
		return;
	}
	input_usage_set(self, "setPrimaryUsagePage:", actual_page);
	input_usage_set(self, "setPrimaryUsage:", actual_usage);
	say("LMI_HID_USAGE_RECHECK restored page=%d usage=%d\n", actual_page, actual_usage);
}

static void
input_usage_install(void)
{
	Class cls = objc_getClass("BKIOHIDService");
	Method method = cls ? class_getInstanceMethod(cls, sel_registerName("_setUpInitialProperties")) : NULL;
	IMP original = method ? method_getImplementation(method) : NULL;
	if (!original || strcmp(method_getTypeEncoding(method), "v16@0:8") != 0 ||
	    (uintptr_t)original != 0x1be1936f4UL + slide || *(const uint32_t *)original != 0xd10203ffU) {
		say("LMI_HID_USAGE_RECHECK hook_refused\n");
		return;
	}
	const char *selectors[] = { "propertyForKey:", "primaryUsagePage", "primaryUsage", "setPrimaryUsagePage:", "setPrimaryUsage:" };
	const char *encodings[] = { "@24@0:8@16", "I16@0:8", "I16@0:8", "v20@0:8I16", "v20@0:8I16" };
	for (unsigned i = 0; i < 5; i++) {
		Method accessor = class_getInstanceMethod(cls, sel_registerName(selectors[i]));
		if (!accessor || strcmp(method_getTypeEncoding(accessor), encodings[i]) != 0) {
			say("LMI_HID_USAGE_RECHECK accessor_refused selector=%s\n", selectors[i]);
			return;
		}
	}
	input_usage_original = (void (*)(id, SEL))original;
	method_setImplementation(method, (IMP)input_usage_initial_properties);
	say("LMI_HID_USAGE_RECHECK installed\n");
}
#endif

/* One frame of the touch screen: the hand, and under it every finger that is down or has just lifted. */
static int
send_touch(IOHIDServiceClientRef screen, const struct redwood_touch *t)
{
	uint32_t change = t->type == REDWOOD_TOUCH_MOVE ? DIGITIZER_POSITION : DIGITIZER_RANGE | DIGITIZER_TOUCH;
	IOHIDEventRef hand, finger;
	bool any = false;
	unsigned f = t->finger;

	if (f >= MAX_FINGERS || (t->type != REDWOOD_TOUCH_DOWN && !fingers[f].touching)) {
		return -1;
	}
	/* A release report can contain the last movement of a short swipe. Keep
	 * that position change in the HID mask as well as the touch transition. */
	if (fingers[f].touching && (fingers[f].x != t->x / 65535.0 || fingers[f].y != t->y / 65535.0)) {
		change |= DIGITIZER_POSITION;
	}
	fingers[f].touching = t->type != REDWOOD_TOUCH_UP;
	fingers[f].x = t->x / 65535.0;
	fingers[f].y = t->y / 65535.0;
	if (t->type == REDWOOD_TOUCH_DOWN) {
		fingers[f].edge = fingers[f].x < EDGE_SIDE || fingers[f].x > 1 - EDGE_SIDE || fingers[f].y < EDGE_TOP ||
		    fingers[f].y > 1 - EDGE_BOTTOM;
	}
	for (unsigned i = 0; i < MAX_FINGERS; i++) {
		any |= fingers[i].touching;
	}

	hand = IOHIDEventCreateDigitizerEvent(NULL, t->time, DIGITIZER_HAND, 0, 0, change & ~DIGITIZER_RANGE, 0, fingers[f].x,
	    fingers[f].y, 0, 0, 0, 0, any, any, 0);
	IOHIDEventSetIntegerValue(hand, FIELD_DIGITIZER_DISPLAY_INTEGRATED, 1);
	IOHIDEventSetIntegerValue(hand, FIELD_IS_BUILT_IN, 1);
	for (unsigned i = 0; i < MAX_FINGERS; i++) {
		if (!fingers[i].touching && i != f) {
			continue;
		}
		finger = IOHIDEventCreateDigitizerFingerEvent(NULL, t->time, i + 1, i + 2,
		    (i == f ? change : 0) | (fingers[i].edge ? DIGITIZER_FROM_EDGE_TIP : 0), fingers[i].x, fingers[i].y, 0,
		    fingers[i].touching ? 1.0 : 0.0, 0, fingers[i].touching, fingers[i].touching, 0);
		IOHIDEventSetIntegerValue(finger, FIELD_DIGITIZER_DISPLAY_INTEGRATED, 1);
		IOHIDEventAppendEvent(hand, finger, 0);
		CFRelease(finger);
	}
	Boolean delivered = IOHIDVirtualServiceClientDispatchEvent(screen, hand);
#ifdef LMI_HID_SIMPLE_RETRY
	static unsigned deliveries, failures;
	if (deliveries++ < 12 || (!delivered && failures++ < 12)) {
		say("LMI_HID_DISPATCH n=%u type=%u accepted=%d\n", deliveries, t->type, delivered != 0);
	}
#else
	(void)delivered;
#endif
	CFRelease(hand);
	return delivered != 0;
}

/*
 * Whether the side button is held right now, for our code in SpringBoard (inject_sb.c,
 * lock_long_press()): kept as the state of a Darwin notification, 2 = held, 1 = released
 * (0, what a name nobody has set says, = not known), and set before the event is sent.
 */
static void
publish_lock_button(bool down)
{
	static int token = NOTIFY_TOKEN_INVALID;

	if (token == NOTIFY_TOKEN_INVALID && notify_register_check("com.redwood.button.lock", &token) != NOTIFY_STATUS_OK) {
		token = NOTIFY_TOKEN_INVALID;
		return;
	}
	notify_set_state(token, down ? 2 : 1);
}

static void
send_button(IOHIDServiceClientRef buttons, const struct redwood_touch *t)
{
	uint32_t usage = t->finger == REDWOOD_BUTTON_LOCK ? HID_USAGE_POWER : t->finger == REDWOOD_BUTTON_HOME ? HID_USAGE_MENU :
	    t->finger == REDWOOD_BUTTON_VOLUME_UP ? HID_USAGE_VOLUME_UP : t->finger == REDWOOD_BUTTON_VOLUME_DOWN ?
	    HID_USAGE_VOLUME_DOWN : 0;
	IOHIDEventRef event;

	if (usage == 0) {
		return;
	}
	if (t->finger == REDWOOD_BUTTON_LOCK) {
		publish_lock_button(t->type == REDWOOD_BUTTON_DOWN);
	}
	event = IOHIDEventCreateKeyboardEvent(NULL, t->time, HID_PAGE_CONSUMER, usage, t->type == REDWOOD_BUTTON_DOWN, 0);
	IOHIDEventSetIntegerValue(event, FIELD_IS_BUILT_IN, 1);
	IOHIDVirtualServiceClientDispatchEvent(buttons, event);
	CFRelease(event);
}

/*
 * Boot-arg touch_lat=1: a line for every touch sample, "tl: i TYPE posted US read US sent US" -- when
 * the kernel stamped it, when this thread had it, when the event system had the event -- in
 * microseconds of mach_absolute_time, the kernel's own time (tools/latency.py).
 */
static bool touch_latency;
static mach_timebase_info_data_t timebase;

static uint64_t
micros(uint64_t absolute)
{
	return absolute * timebase.numer / timebase.denom / 1000;
}

#ifdef LMI_INPUT_TRACE
extern void IOHIDEventSystemClientRegisterEventCallback(IOHIDEventSystemClientRef client,
    void (*callback)(void *, void *, void *, IOHIDEventRef), void *target, void *refcon);
extern uint32_t IOHIDEventGetType(IOHIDEventRef event);
extern uint64_t IOHIDEventGetTimeStamp(IOHIDEventRef event);
extern uint64_t IOHIDEventGetSenderID(IOHIDEventRef event);

/* A receiving monitor is independent of the service's dispatch return value.
 * It observes the event server without replacing its client or changing events.
 * This still does not prove delivery to SpringBoard or an application's UI. */
static void
input_observed(__unused void *target, __unused void *refcon, __unused void *sender, IOHIDEventRef event)
{
	static unsigned count;
	if (event == NULL || IOHIDEventGetType(event) != 11 || count >= 192) {
		return;
	}
	count++;
	say("LMI_HID_OBSERVED n=%u posted_us=%llu observed_us=%llu sender=%llu\n", count,
	    micros(IOHIDEventGetTimeStamp(event)), micros(mach_absolute_time()), IOHIDEventGetSenderID(event));
}

static void
input_monitor_start(void)
{
	IOHIDEventSystemClientRef monitor = IOHIDEventSystemClientCreateWithType(NULL, 1, NULL); /* monitor */
	if (monitor == NULL) {
		say("LMI_HID_MONITOR unavailable\n");
		return;
	}
	IOHIDEventSystemClientRegisterEventCallback(monitor, input_observed, NULL, NULL);
	IOHIDEventSystemClientScheduleWithDispatchQueue(monitor, dispatch_queue_create("redwood.input-monitor", NULL));
	say("LMI_HID_MONITOR scheduled\n");
	/* Keep the created reference for the bounded RAM run, like the sending client. */
}
#endif

#ifdef LMI_HID_ROUTING_TRACE
/* Bounded observation of the stock BackBoard processor, without os_log's
 * startup overhead. Both wrappers preserve every argument and return value.
 * The exact method encodings, image-relative IMPs and first instructions are
 * from the standalone iOS 16.5 20F66 backboardd, not the shared cache. */
static long (*routing_process_original)(id, SEL, IOHIDEventRef *, id, id);
static id (*routing_service_original)(id, SEL, IOHIDEventRef, id, bool *);
static id (*routing_state_original)(id, SEL, id);
static unsigned routing_process_count, routing_service_count;
static unsigned routing_state_count;

static id
routing_state(id self, SEL cmd, id service)
{
	id state = routing_state_original(self, cmd, service);
	unsigned n = __atomic_add_fetch(&routing_state_count, 1, __ATOMIC_RELAXED);
	if (n <= 4) {
		char text[1024] = "nil_or_description_unavailable";
		CFStringRef description = state ? CFCopyDescription((CFTypeRef)state) : NULL;
		if (description) {
			CFStringGetCString(description, text, sizeof(text), kCFStringEncodingUTF8);
			CFRelease(description);
		}
		for (size_t pos = 0; pos < strlen(text); pos += 160) {
			say("LMI_BK_STATE n=%u part=%zu state=%p %.160s\n", n, pos / 160, state, text + pos);
		}
	}
	return state;
}

static long
routing_process(id self, SEL cmd, IOHIDEventRef *event, id sender, id dispatcher)
{
	bool digitizer = event && *event && IOHIDEventGetType(*event) == 11;
	uint64_t timestamp = digitizer ? IOHIDEventGetTimeStamp(*event) : 0;
	long result = routing_process_original(self, cmd, event, sender, dispatcher);
	if (digitizer) {
		unsigned n = __atomic_add_fetch(&routing_process_count, 1, __ATOMIC_RELAXED);
		if (n <= 32) {
			say("LMI_BK_PROCESS n=%u posted_us=%llu result=%ld sender_class=%s\n", n,
			    micros(timestamp), result, sender ? object_getClassName(sender) : "nil");
		}
	}
	return result;
}

static id
routing_service(id self, SEL cmd, IOHIDEventRef event, id sender, bool *from_touchpad)
{
	id service = routing_service_original(self, cmd, event, sender, from_touchpad);
	if (event && IOHIDEventGetType(event) == 11) {
		unsigned n = __atomic_add_fetch(&routing_service_count, 1, __ATOMIC_RELAXED);
		if (n <= 32) {
			say("LMI_BK_SERVICE n=%u posted_us=%llu service=%p touchpad=%d sender_class=%s\n", n,
			    micros(IOHIDEventGetTimeStamp(event)), service,
			    from_touchpad ? *from_touchpad : -1, sender ? object_getClassName(sender) : "nil");
		}
		if (n <= 2 && service) {
			char text[1024] = "description_unavailable";
			CFStringRef description = CFCopyDescription((CFTypeRef)service);
			if (description) {
				CFStringGetCString(description, text, sizeof(text), kCFStringEncodingUTF8);
				CFRelease(description);
			}
			for (size_t pos = 0; pos < strlen(text); pos += 160) {
				say("LMI_BK_SERVICE_INFO n=%u part=%zu %.160s\n", n, pos / 160, text + pos);
			}
		}
	}
	return service;
}

static IMP
routing_replace(const char *name, const char *encoding, uintptr_t expected, uint32_t instruction, IMP wrapper)
{
	Class cls = objc_getClass("BKHIDDirectTouchEventProcessor");
	Method method = cls ? class_getInstanceMethod(cls, sel_registerName(name)) : NULL;
	IMP original = method ? method_getImplementation(method) : NULL;
	const char *reason = !cls ? "class_missing" : !method ? "method_missing" : !original ? "no_imp" :
	    strcmp(method_getTypeEncoding(method), encoding) != 0 ? "abi_mismatch" :
	    (uintptr_t)original != expected ? "address_mismatch" :
	    *(const uint32_t *)original != instruction ? "instruction_mismatch" : NULL;
	if (reason) {
		say("LMI_BK_HOOK selector=%s skipped=%s original=%p expected=%p\n", name, reason,
		    original, (void *)expected);
		return NULL;
	}
	/* Publish the original before replacing the method. The input thread has
	 * not started reading or dispatching the physical samples yet. */
	if (wrapper == (IMP)routing_process) {
		routing_process_original = (long (*)(id, SEL, IOHIDEventRef *, id, id))original;
	} else if (wrapper == (IMP)routing_service) {
		routing_service_original = (id (*)(id, SEL, IOHIDEventRef, id, bool *))original;
	} else {
		routing_state_original = (id (*)(id, SEL, id))original;
	}
	method_setImplementation(method, wrapper);
	say("LMI_BK_HOOK selector=%s installed\n", name);
	return original;
}

static void
input_routing_watch(void)
{
	/* Match the loaded executable's header, without assuming that dyld index
	 * zero or the shared-cache slide describes this standalone Mach-O image. */
	uintptr_t image_base = 0;
	for (uint32_t i = 0; i < _dyld_image_count(); i++) {
		const char *path = _dyld_get_image_name(i);
		const char *name = path ? strrchr(path, '/') : NULL;
		if (path && strcmp(name ? name + 1 : path, "backboardd") == 0) {
			image_base = (uintptr_t)_dyld_get_image_header(i);
			break;
		}
	}
	if (!image_base) {
		say("LMI_BK_HOOK executable_header_missing\n");
		return;
	}
	routing_replace("processEvent:sender:dispatcher:", "q40@0:8N^^{__IOHIDEvent}16@24@32",
	    image_base + 0x3aea0UL, 0xd10243ffU, (IMP)routing_process);
	routing_replace("_determineServiceForEvent:sender:fromTouchPad:", "@40@0:8^{__IOHIDEvent=}16@24^B32",
	    image_base + 0x3cba0UL, 0xd10183ffU, (IMP)routing_service);
	routing_replace("_queue_digitizerStateForService:", "@24@0:8@16",
	    image_base + 0x3c1a8UL, 0xa9bd57f6U, (IMP)routing_state);
}
#endif

static void *
input_thread(__unused void *arg)
{
#ifdef LMI_HID_SIMPLE_RETRY
	static const int types[] = { HID_CLIENT_SIMPLE };
#else
	static const int types[] = { HID_CLIENT_SIMPLE, HID_CLIENT_RATE_CONTROLLED };
#endif
	IOHIDEventSystemClientRef client = NULL;
	IOHIDServiceClientRef screen = NULL, buttons = NULL;
	struct redwood_touch t;
	unsigned count = 0, waking = 0;         /* waking: the fingers whose touch went into waking the display */
	int device;

	pthread_setname_np("redwood input");
	{
		char arguments[1024] = "";
		size_t size = sizeof(arguments) - 1;

		if (sysctlbyname("kern.bootargs", arguments, &size, NULL, 0) == 0) {
			touch_latency = strstr(arguments, "touch_lat=1") != NULL;
		}
		mach_timebase_info(&timebase);
#ifdef LMI_INPUT_TRACE
		say("LMI_INPUT_TIMEBASE numer=%u denom=%u now=%llu\n", timebase.numer, timebase.denom,
		    mach_absolute_time());
#endif
	}
	device = open(REDWOOD_TOUCH_DEVICE, O_RDONLY);
	if (device < 0) {
		say("redwood: input: %s: %s\n", REDWOOD_TOUCH_DEVICE, strerror(errno));
		return NULL;
	}
	sleep(3);                       /* let backboardd get as far as starting its event server */
	for (unsigned i = 0; screen == NULL && i < sizeof(types) / sizeof(types[0]); i++) {
		/* this waits until the server (this very program) answers */
		client = IOHIDEventSystemClientCreateWithType(NULL, types[i], NULL);
		if (client == NULL) {
			say("redwood: input: no HID client of type %d\n", types[i]);
			continue;
		}
		IOHIDEventSystemClientScheduleWithDispatchQueue(client, dispatch_queue_create("redwood.input", NULL));
		screen = make_service(client, "Redwood touch screen", HID_PAGE_DIGITIZER, HID_USAGE_TOUCH_SCREEN, true);
		if (screen == NULL) {
			say("redwood: input: a HID client of type %d may not create services\n", types[i]);
		}
	}
	if (screen != NULL) {
		buttons = make_service(client, "Redwood buttons", HID_PAGE_CONSUMER, HID_USAGE_CONSUMER_CONTROL, false);
	}
	say("redwood: input: touch screen service %p, buttons %p\n", (void *)screen, (void *)buttons);
	dispatch_semaphore_signal(input_services_made); /* see wait_for_als_arrival() */
	if (screen == NULL) {
		return NULL;
	}
#ifdef LMI_HID_ROUTING_TRACE
	input_routing_watch();
#endif
#ifdef LMI_INPUT_TRACE
	input_monitor_start();
#endif

	while (read(device, &t, sizeof(t)) == (ssize_t)sizeof(t)) {
		uint64_t read_at = mach_absolute_time();
		int accepted = -1;
		const char *route = "button";

		if (count++ < 4) {
			say("redwood: input: sample type %u finger %u at %u %u\n", t.type, t.finger, t.x, t.y);
		}
		if (t.type > REDWOOD_TOUCH_UP) {
			if (buttons != NULL) {
				send_button(buttons, &t);
			}
		} else if (t.type == REDWOOD_TOUCH_DOWN && (touch_mode & 0xff) == TOUCH_MODE_WAKE && buttons != NULL) {
			route = "wake";
			/*
			 * The display is off and a tap is to wake it. The lock button is what wakes it here:
			 * press it for the finger, and keep the rest of this touch to ourselves.
			 */
			struct redwood_touch press = { .time = t.time, .type = REDWOOD_BUTTON_DOWN, .finger = REDWOOD_BUTTON_LOCK };

			send_button(buttons, &press);
			press.type = REDWOOD_BUTTON_UP;
			send_button(buttons, &press);
			waking |= 1u << (t.finger & 31);
		} else if (waking & (1u << (t.finger & 31))) {
			route = "waking";
			if (t.type == REDWOOD_TOUCH_UP) {
				waking &= ~(1u << (t.finger & 31));
			}
		} else {
			route = "touch";
			accepted = send_touch(screen, &t);
			if (touch_latency) {
				say("tl: i %u posted %llu read %llu sent %llu\n", t.type, micros(t.time), micros(read_at),
				    micros(mach_absolute_time()));
			}
		}
#ifdef LMI_INPUT_TRACE
		/* Bounded diagnostic build: observe the original sample and delivery
		 * times without changing its coordinates, phases or HID timestamp. */
		if (count <= 192) {
			say("LMI_INPUT_SAMPLE n=%u type=%u finger=%u x=%u y=%u posted_us=%llu read_us=%llu sent_us=%llu route=%s accepted=%d mode=%d\n",
			    count, t.type, t.finger, t.x, t.y, micros(t.time), micros(read_at),
			    micros(mach_absolute_time()), route, accepted, touch_mode);
			if (count == 192) {
				say("LMI_INPUT_TRACE_LIMIT 192\n");
			}
		}
#endif
		(void)accepted;
		(void)route;
	}
	say("redwood: input: %s: %s\n", REDWOOD_TOUCH_DEVICE, strerror(errno));
	return NULL;
}

static void
input_start(void)
{
	pthread_t thread;

	input_services_made = dispatch_semaphore_create(0);
	if (pthread_create(&thread, NULL, input_thread, NULL) == 0) {
		pthread_detach(thread);
	}
}

/* ---- containermanagerd ---------------------------------------------------------------------------- */

static BOOL
personas_are_supported(__unused id self, __unused SEL selector)
{
	return NO;
}

static void
container_manager_fixes(void)
{
	Class cls = objc_getClass("MCMUserIdentityCache");
	Method method = cls ? class_getClassMethod(cls, sel_registerName("personasAreSupported")) : NULL;
	IMP original = method ? method_getImplementation(method) : NULL;

	if (original == NULL || (uintptr_t)original != 0x1c3ea6298UL + slide) {
		say("redwood: +[MCMUserIdentityCache personasAreSupported]: found %#lx, not what was expected; left alone\n",
		    original ? (uintptr_t)original - slide : 0);
		return;
	}
	method_setImplementation(method, (IMP)personas_are_supported);
	say("redwood: container manager: no personas\n");
}

#ifdef LMI_LSD_SINGLE_USER
/* In the RAM-only single-user port there are no persona volumes. lsd's
 * InstalledContentLibrary enumerates them once per bundle while seeding its
 * database; the stock synchronous usermanagerd query blocks its clients.
 * An empty successful list keeps the stock default-persona fallback in
 * __GetEligiblePersonaForBundle, without inventing identities or containers. */
static CFArrayRef lsd_personas;
static id
lsd_persona_attributes(__unused id self, __unused SEL selector, id *error)
{
	static unsigned calls;
	unsigned count = __atomic_add_fetch(&calls, 1, __ATOMIC_RELAXED);
	if (error != NULL) {
		*error = nil;
	}
	if (count <= 4) {
		say("LMI_LSD_PERSONAS_EMPTY call=%u\n", count);
	}
	return (id)lsd_personas;
}

static void
lsd_single_user_fixes(void)
{
	void *framework = dlopen("/System/Library/PrivateFrameworks/UserManagement.framework/UserManagement", RTLD_LAZY);
	Class cls = framework ? objc_getClass("UMUserManager") : Nil;
	Method method = cls ? class_getInstanceMethod(cls, sel_registerName("listAllPersonaAttributesWithError:")) : NULL;
	IMP original = method ? method_getImplementation(method) : NULL;
	if ((uintptr_t)original != 0x1920d35e8UL + slide ||
	    *(const uint32_t *)original != 0xd10583ffU || method_getNumberOfArguments(method) != 3) {
		say("LMI_LSD_PERSONAS_SKIPPED original=%#lx\n", original ? (uintptr_t)original - slide : 0);
		return;
	}
	lsd_personas = CFArrayCreate(NULL, NULL, 0, &kCFTypeArrayCallBacks);
	if (lsd_personas != NULL) {
		method_setImplementation(method, (IMP)lsd_persona_attributes);
		say("LMI_LSD_PERSONAS_INSTALLED single-user empty list\n");
	}
}
#endif

/* ---------------------------------------------------------------------------------------------- */

/*
 * An OpenGL ES implementation for CoreAnimation (src/eagl.c, Mesa behind it): loaded, it puts
 * itself behind EAGLContext, and the renderer the server then gets is the OpenGL ES one. That
 * is worth it where a GPU does the drawing, and only there: on the phone, when the kernel has
 * started the GPU and keeps it (boot-arg gpu=1), which the service RedwoodGPU says (it is there
 * before the first program runs, or not at all). Everywhere else -- QEMU, a run without the
 * boot-arg, a phone without the GPU's firmware in the image, a GPU that did not start --
 * nothing is loaded, and CoreAnimation draws with its own software renderer as in an image
 * without the library.
 * Boot-arg gl=0: not even with a GPU; gl=1: also without one, by Mesa's software driver (slow;
 * for working on eagl.c in QEMU).
 */
static void
opengl_es(void)
{
	char arguments[1024] = "";
	size_t size = sizeof(arguments) - 1;
	const char *argument;
	io_service_t gpu;
	void *library;
	int wanted = -1, told = 0;

	if (access(REDWOOD_GL, R_OK) != 0) {
		return;                                 /* (an image built without it) */
	}
	if (sysctlbyname("kern.bootargs", arguments, &size, NULL, 0) == 0) {
		functions_said_yes(arguments);
		compile_shaders_said = strstr(arguments, "glcompile=1") != NULL;
		for (argument = arguments; (argument = strstr(argument, "gl=")) != NULL; argument += 3) {
			if (argument == arguments || argument[-1] == ' ') {
				wanted = argument[3] != '0';
				told = 1;
			}
		}
	}
	if (wanted < 0) {
		gpu = IOServiceGetMatchingService(0, IOServiceMatching("RedwoodGPU"));
		wanted = gpu != 0;
		if (gpu != 0) {
			IOObjectRelease(gpu);
		}
	}
	if (!wanted) {
		say("redwood: %s: CoreAnimation keeps its software renderer\n", told ? "gl=0" : "no GPU to draw with");
		return;
	}
	if ((library = dlopen(REDWOOD_GL, RTLD_NOW)) == NULL) {
		say("redwood: %s: %s\n", REDWOOD_GL, dlerror());
		return;
	}
	gl_loaded = 1;
	gl_function_values = (void (*)(void *, unsigned, unsigned, size_t, size_t, const float *))dlsym(library,
	    "redwood_gl_function_values");
	gl_function_refused = (void (*)(unsigned))dlsym(library, "redwood_gl_function_refused");
}

__attribute__((constructor))
static void
redwood_init(void)
{
	const char *name = getprogname();
	size_t length = 0;
	const void *cache = _dyld_get_shared_cache_range(&length);

	if (name == NULL || cache == NULL) {
		return;
	}
	slide = (uintptr_t)cache - CACHE_BASE;
	if (strcmp(name, "backboardd") == 0) {
		char arguments[1024] = "";
		size_t size = sizeof(arguments) - 1;

		/*
		 * Boot-arg ca_vbl=1: CoreAnimation's frame clock from the display driver's refresh
		 * notifications. QuartzCore takes them (IOMobileFramebufferEnableVSyncNotifications) only on
		 * the phones with an A7 to A10, or when CA_FORCE_TIMER is in the environment
		 * (CADeviceUseVBL()); on the iPhone X it runs a timer of its own instead (CADisplayTimer),
		 * whose phase it would set from the frame timings of a display driver this one is not.
		 */
		if (sysctlbyname("kern.bootargs", arguments, &size, NULL, 0) == 0 && strstr(arguments, "ca_vbl=1") != NULL) {
			setenv("CA_FORCE_TIMER", "1", 1);
			say("redwood: ca_vbl=1: CoreAnimation is to take the display driver's refresh notifications\n");
		}
		/*
		 * Boot-arg caenv=NAME=VALUE (as many as wanted): into the window server's environment, for
		 * CoreAnimation's own switches (CA_LOG_TRIPLE_BUFFERING=1, CA_FORCE_DOUBLE_BUFFERING=1 ...).
		 */
		for (const char *argument = arguments; (argument = strstr(argument, "caenv=")) != NULL; argument += 6) {
			char setting[128];
			size_t length = strcspn(argument + 6, " ");
			char *equals;

			if ((argument != arguments && argument[-1] != ' ') || length == 0 || length >= sizeof(setting)) {
				continue;
			}
			memcpy(setting, argument + 6, length);
			setting[length] = 0;
			if ((equals = strchr(setting, '=')) != NULL) {
				*equals = 0;
				setenv(setting, equals + 1, 1);
				say("redwood: caenv: %s=%s for the window server\n", setting, equals + 1);
			}
		}
		opengl_es();
		window_server_fixes();
		/*
		 * brightness_fixes() is not used for now: with it backboardd no longer took our touch
		 * screen service for its own ("still waiting for a main screen digitizer"), whether the
		 * service was made before or after the touch processing starts. (Most likely it only
		 * moved the start of the event server onto the moment make_service() now knows how to
		 * survive; not tried again since, and until it is, the five seconds stay.)
		 */
#ifdef LMI_HID_USAGE_RECHECK
		input_usage_install();
#endif
		input_start();
	} else if (strncmp(name, "containermanagerd", 17) == 0) {
		container_manager_fixes();
	}
#ifdef LMI_LSD_SINGLE_USER
	else if (strcmp(name, "lsd") == 0) {
		lsd_single_user_fixes();
	}
#endif
}
