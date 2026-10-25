"""Run upstream image census with the reviewed pinned apfsck archive build."""
import importlib.util
from pathlib import Path
root=Path('/root/hackios-lmi/hackios')
path=root/'tools/apfs/check-image.py'
spec=importlib.util.spec_from_file_location('check_apfs_image',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.APFSCK='/root/hackios-lmi/apfsprogs-pinned/apfsck/apfsck'
module.main()
