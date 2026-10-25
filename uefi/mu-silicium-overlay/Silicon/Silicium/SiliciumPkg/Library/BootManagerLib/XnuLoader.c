/**
  lmi first-boot diagnostics. Display status without accessing raw partitions,
  payload addresses or persistence markers. This does not launch XNU.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/UefiLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Protocol/GraphicsOutput.h>
#include <Protocol/UsbFunctionIo.h>

#include "XnuLoader.h"
#include "LmiUsbProbe.h"

STATIC EFI_GUID mUsbDeviceGuid = {0xd9d9ce48,0x44b8,0x4f49,{0x8e,0x3e,0x2a,0x3b,0x92,0x7d,0xc6,0xc1}};
STATIC EFI_GUID mUsbInitGuid = {0x1c0cffce,0xfc8d,0x4e44,{0x8c,0x78,0x9c,0x9e,0x5b,0x53,0x0d,0x36}};

STATIC VOID EFIAPI
UsbInitNotify (IN EFI_EVENT Event, IN VOID *Context)
{
  (VOID)Event;
  (VOID)Context;
}

VOID
XnuLoaderMain (VOID)
{
  EFI_STATUS                    Status;
  EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop = NULL;
  EFI_USBFN_IO_PROTOCOL        *Usb = NULL;
  UINT64                        CurrentEl;
  UINT64                        Mpidr;
  UINT64                        Mmfr0;
  EFI_EVENT                     UsbInitEvent;
  VOID                         *UsbDevice = NULL;

  __asm__ volatile ("mrs %0, CurrentEL" : "=r" (CurrentEl));
  __asm__ volatile ("mrs %0, MPIDR_EL1" : "=r" (Mpidr));
  __asm__ volatile ("mrs %0, ID_AA64MMFR0_EL1" : "=r" (Mmfr0));
  Print (L"\r\nHackiOS lmi UEFI diagnostics\r\n");
  Print (L"Diagnostic revision 2\r\n");
  Print (L"CPU: EL%lu MPIDR=%lx\r\n", CurrentEl >> 2, Mpidr);
  Print (L"MMFR0=%lx TGran16=%lx\r\n", Mmfr0, (Mmfr0 >> 20) & 0xf);

  Status = gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&Gop);
  Print (L"GraphicsOutput: %r\r\n", Status);
  if (!EFI_ERROR (Status) && Gop->Mode != NULL && Gop->Mode->Info != NULL) {
    Print (L"Framebuffer: %lx size=%lx\r\n", Gop->Mode->FrameBufferBase,
           (UINT64)Gop->Mode->FrameBufferSize);
    Print (L"Display: %ux%u stride=%u format=%u\r\n",
           Gop->Mode->Info->HorizontalResolution, Gop->Mode->Info->VerticalResolution,
           Gop->Mode->Info->PixelsPerScanLine, Gop->Mode->Info->PixelFormat);
  }

  Status = gBS->LocateProtocol (&gEfiUsbFunctionIoProtocolGuid, NULL, (VOID **)&Usb);
  Print (L"UsbFunctionIo: %r\r\n", Status);
  // Follow xnuloader/loader.c::usb_start's platform initialization sequence.
  // Only locate the protocol here; no USB descriptors or transfers are started.
  Status = gBS->LocateProtocol (&mUsbDeviceGuid, NULL, &UsbDevice);
  Print (L"Qcom UsbDevice before init: %r\r\n", Status);
  Status = gBS->CreateEventEx (EVT_NOTIFY_SIGNAL, TPL_CALLBACK,
                              UsbInitNotify, NULL, &mUsbInitGuid, &UsbInitEvent);
  Print (L"USB init event: %r\r\n", Status);
  if (!EFI_ERROR (Status)) {
    Status = gBS->SignalEvent (UsbInitEvent);
    Print (L"USB init signal: %r\r\n", Status);
    gBS->CloseEvent (UsbInitEvent);
  }
  Status = gBS->LocateProtocol (&mUsbDeviceGuid, NULL, &UsbDevice);
  Print (L"Qcom UsbDevice after init: %r\r\n", Status);
  Status = gBS->LocateProtocol (&gEfiUsbFunctionIoProtocolGuid, NULL, (VOID **)&Usb);
  Print (L"UsbFunctionIo after init: %r\r\n", Status);
  {
    EFI_HANDLE Handle = NULL;
    Print (L"Starting lmi loader USB bring-up; 600-second timeout for RAM image staging.\r\n");
    Status = gBS->LoadImage (FALSE, gImageHandle, NULL,
                            (VOID *)mLmiUsbProbe, sizeof (mLmiUsbProbe), &Handle);
    Print (L"USB probe LoadImage: %r\r\n", Status);
    if (!EFI_ERROR (Status)) {
      Status = gBS->StartImage (Handle, NULL, NULL);
      Print (L"USB probe returned: %r\r\n", Status);
      gBS->UnloadImage (Handle);
    }
  }
  Print (L"Diagnostics only. Returning to Android in 30 seconds.\r\n");
  gBS->Stall (30000000);
  gRT->ResetSystem (EfiResetCold, EFI_SUCCESS, 0, NULL);
  CpuDeadLoop ();
}
