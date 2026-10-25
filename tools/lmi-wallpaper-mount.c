/* Mount the original wallpaper collection with software-decodable PNG assets.
 * Both paths are RAM disks. Runs synchronously before original launchd.
 */
#include "mini.h"
int main(int argc,char **argv,char **envp) {
    (void)argc;(void)argv;(void)envp;
    const char *from="/redwood/Wallpaper/iOS_16~iphone.wallpaperCollection";
    const char *to="/Library/Wallpaper/Collections/iOS_16~iphone.wallpaperCollection";
    int result=mount("bindfs",to,MNT_RDONLY,(void *)from);
    printf("LMI_WALLPAPER_PNG_MOUNT result=%d errno=%d\n",result,result?errno:0);
    /* bindfs permits unsigned init only as PID1. rc must exec this helper,
     * which then keeps PID1 while handing over to original Apple launchd.
     */
    char *args[]={"/sbin/launchd.ios",0};
    execve(args[0],args,envp);
    printf("LMI_WALLPAPER_LAUNCHD_EXEC_FAILED errno=%d\n",errno);
    return 1;
}
