"""Read-only original IPSW wallpaper audit, run in WSL."""
from pathlib import Path
import json, plistlib
root=Path('/root/hackios-lmi/hackios/ios165/rootfs')
out=Path(__file__).resolve().parents[1]/'out/lmi-touch-research'
result={}
for name in ['Library/Wallpaper/DefaultWallpapers~iphone.plist',
             'Library/Wallpaper/Collections/iOS_16~iphone.wallpaperCollection/WallpaperCollection.plist']:
    result[name]=plistlib.loads((root/name).read_bytes())
result['extensions']=[str(p.relative_to(root)) for p in root.rglob('CollectionsPoster.appex')]
result['ios16_resources']=[str(p.relative_to(root)) for p in (root/'Library/Wallpaper/Collections/iOS_16~iphone.wallpaperCollection').rglob('*') if p.is_file()]
text=json.dumps(result,indent=2,default=str)
(out/'original-wallpaper-audit.json').write_text(text+'\n')
print(text[:14000])
