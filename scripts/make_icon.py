from pathlib import Path
from PIL import Image, ImageDraw

out = Path(__file__).resolve().parent.parent / 'assets' / 'app.ico'
im = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.rounded_rectangle((4, 4, 252, 252), radius=55, fill='#2f5145')
for y in (62, 106):
    d.rounded_rectangle((65, y, 191, y + 28), radius=5, outline='#e9e8dc', width=6)
d.rounded_rectangle((65, 150, 155, 178), radius=5, fill='#e9e8dc')
im.save(out, sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print(out)
