"""Create an isolated original iOS16 wallpaper resource variant (WSL heif venv).
No image or source is overwritten. Does not claim hardware validation.
"""
from pathlib import Path
import hashlib,json,re,shutil,urllib.parse
from PIL import Image
import pillow_heif
pillow_heif.register_heif_opener()
repo=Path(__file__).resolve().parents[1]
src=Path('/root/hackios-lmi/hackios/ios165/rootfs/Library/Wallpaper/Collections/iOS_16~iphone.wallpaperCollection')
out=repo/'out/lmi-wallpaper-png-resources'
assert not out.exists(), 'Preserve completed artifact'
shutil.copytree(src,out)
records=[]
for caml in out.rglob('main.caml'):
    text=caml.read_text()
    for name in sorted(set(re.findall(r'src="([^\"]+\.HEIC)"',text))):
        old=caml.parent/urllib.parse.unquote(name)
        new=old.with_suffix('.png')
        with Image.open(old) as im:
            im.load()
            mode='RGBA' if 'A' in im.getbands() else 'RGB'
            im.convert(mode).save(new)
            dims=im.size
        with Image.open(new) as check:
            check.load();assert check.size==dims
        text=text.replace('src="'+name+'"','src="'+name[:-5]+'.png"')
        records.append(dict(path=str(new.relative_to(out)),size=dims,
            source_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),png_sha256=hashlib.sha256(new.read_bytes()).hexdigest()))
    assert not re.search(r'src="[^\"]+\.HEIC"',text)
    caml.write_text(text)
audit=dict(source=str(src),output=str(out),changes='Only original CGImage HEIC sources converted to PNG; original CAML layers/animation/layout preserved',
    tested_on_hardware=False,decoder=pillow_heif.__version__,records=records)
(out/'conversion-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
print(json.dumps(audit,indent=2))
