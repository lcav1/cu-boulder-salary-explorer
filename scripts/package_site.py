"""Stage only public app assets for Pages; never publish tooling or test files."""
from pathlib import Path
import shutil
ROOT = Path(__file__).resolve().parents[1]
output = ROOT / '_site'
output.mkdir(exist_ok=True)
for filename in ['index.html']:
    shutil.copy2(ROOT / filename, output / filename)
for directory in ['assets', 'data']:
    shutil.copytree(ROOT / directory, output / directory, dirs_exist_ok=True)
(output / '.nojekyll').touch()
print(f'Packaged public app in {output}')
