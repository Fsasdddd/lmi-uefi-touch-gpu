static void
control_target_to_surface(struct eagl *e, struct image *image)
{
	IOSurfaceRef surface = image->surface;
	size_t row = IOSurfaceGetBytesPerRow(surface);
	uint8_t *base;

	image->drawn = false;
	if (image->mirror != 0) {
		GLint read = 0, draw = 0;

		/* the frame into the surface's memory, by the GPU (blit_targets); upside down if it is drawn so */
		glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &read);
		glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &draw);
		if (e->reader == 0) {
			glGenFramebuffers(1, &e->reader);
		}
		if (e->writer == 0) {
			glGenFramebuffers(1, &e->writer);
		}
		glBindFramebuffer(GL_READ_FRAMEBUFFER, e->reader);
		glFramebufferTexture2D(GL_READ_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, image->texture, 0);
		glBindFramebuffer(GL_DRAW_FRAMEBUFFER, e->writer);
		glFramebufferTexture2D(GL_DRAW_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, image->mirror, 0);
		glBlitFramebuffer(0, 0, image->width, image->height, 0, image->invert ? image->height : 0, image->width,
		    image->invert ? 0 : image->height, GL_COLOR_BUFFER_BIT, GL_NEAREST);
		glBindFramebuffer(GL_READ_FRAMEBUFFER, (GLuint)read);
		glBindFramebuffer(GL_DRAW_FRAMEBUFFER, (GLuint)draw);
		if (IOSurfaceLock(surface, 0, NULL) == 0) {
			IOSurfaceUnlock(surface, 0, NULL);
		}
		return;
	}
	if (image->shared) {
		/* whoever looks at the surface's seed is to see that it has changed */
		if (IOSurfaceLock(surface, 0, NULL) == 0) {
			IOSurfaceUnlock(surface, 0, NULL);
		}
		return;
	}
	if (e->reader == 0) {
		glGenFramebuffers(1, &e->reader);
	}
	glBindFramebuffer(GL_FRAMEBUFFER, e->reader);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, image->texture, 0);
	if (IOSurfaceLock(surface, 0, NULL) == 0) {
		base = IOSurfaceGetBaseAddress(surface);
		glPixelStorei(GL_PACK_ROW_LENGTH, (GLint)(row / 4));
		glPixelStorei(GL_PACK_ALIGNMENT, 4);
		if (!image->invert) {
			glReadPixels(0, 0, image->width, image->height, GL_BGRA, GL_UNSIGNED_BYTE, base);
		} else {
			for (GLsizei y = 0; y < image->height; y++) {
				glReadPixels(0, y, image->width, 1, GL_BGRA, GL_UNSIGNED_BYTE, base + row * (size_t)(image->height - 1 - y));
			}
		}
		glPixelStorei(GL_PACK_ROW_LENGTH, 0);
		IOSurfaceUnlock(surface, 0, NULL);
	}
	glBindFramebuffer(GL_FRAMEBUFFER, e->framebuffer);
}

static void
target_to_surface(struct eagl *e, struct image *image)
{
	IOSurfaceRef surface = image->surface;
	size_t row = IOSurfaceGetBytesPerRow(surface);
	uint8_t *base;

	image->drawn = false;
	if (image->mirror != 0) {
		GLint read = 0, draw = 0;
		GLboolean scissored = glIsEnabled(GL_SCISSOR_TEST);

		/* the frame into the surface's memory, by the GPU (blit_targets); upside down if it is drawn so */
		glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &read);
		glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &draw);
		if (e->reader == 0) {
			glGenFramebuffers(1, &e->reader);
		}
		if (e->writer == 0) {
			glGenFramebuffers(1, &e->writer);
		}
		glBindFramebuffer(GL_READ_FRAMEBUFFER, e->reader);
		glFramebufferTexture2D(GL_READ_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, image->texture, 0);
		glBindFramebuffer(GL_DRAW_FRAMEBUFFER, e->writer);
		glFramebufferTexture2D(GL_DRAW_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, image->mirror, 0);
		/* The surface needs the whole frame, including pixels outside the last
		 * CoreAnimation damage rectangle. Blits also obey destination scissor. */
		glDisable(GL_SCISSOR_TEST);
		glBlitFramebuffer(0, 0, image->width, image->height, 0, image->invert ? image->height : 0, image->width,
		    image->invert ? 0 : image->height, GL_COLOR_BUFFER_BIT, GL_NEAREST);
		if (scissored) {
			glEnable(GL_SCISSOR_TEST);
		}
		glBindFramebuffer(GL_READ_FRAMEBUFFER, (GLuint)read);
		glBindFramebuffer(GL_DRAW_FRAMEBUFFER, (GLuint)draw);
		if (IOSurfaceLock(surface, 0, NULL) == 0) {
			IOSurfaceUnlock(surface, 0, NULL);
		}
		return;
	}
	if (image->shared) {
		/* whoever looks at the surface's seed is to see that it has changed */
		if (IOSurfaceLock(surface, 0, NULL) == 0) {
			IOSurfaceUnlock(surface, 0, NULL);
		}
		return;
	}
	if (e->reader == 0) {
		glGenFramebuffers(1, &e->reader);
	}
	glBindFramebuffer(GL_FRAMEBUFFER, e->reader);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, image->texture, 0);
	if (IOSurfaceLock(surface, 0, NULL) == 0) {
		base = IOSurfaceGetBaseAddress(surface);
		glPixelStorei(GL_PACK_ROW_LENGTH, (GLint)(row / 4));
		glPixelStorei(GL_PACK_ALIGNMENT, 4);
		if (!image->invert) {
			glReadPixels(0, 0, image->width, image->height, GL_BGRA, GL_UNSIGNED_BYTE, base);
		} else {
			for (GLsizei y = 0; y < image->height; y++) {
				glReadPixels(0, y, image->width, 1, GL_BGRA, GL_UNSIGNED_BYTE, base + row * (size_t)(image->height - 1 - y));
			}
		}
		glPixelStorei(GL_PACK_ROW_LENGTH, 0);
		IOSurfaceUnlock(surface, 0, NULL);
	}
	glBindFramebuffer(GL_FRAMEBUFFER, e->framebuffer);
}
