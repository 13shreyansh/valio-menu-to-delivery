"""Authored handwriting-style sample boards. No OCR answer is embedded in the JPEGs."""
from PIL import Image,ImageDraw,ImageFont,ImageFilter
import random
from pathlib import Path
FONT='artifacts/font-source/caveat.ttf'
boards=[
 ['SATURDAY WEDDING  /  120 guests','FINAL MENU','Paistettu siika     120','Lemon tart          120','Juustolautanen      140','No Lohikeitto'],
 ['Lauantai 21.11.  /  120 vierasta','LOPULLINEN MENU','Paistettu siika    120 annosta','Sitruunatorttu     120 annosta','Juustolautanen     140 annosta','Ei lohikeittoa'],
 ['Kitchen: Saturday wedding','120 guests - FINAL','Fried whitefish       120','Lemon tart            120','Cheese board          140','Remove salmon soup'],
]
for index,lines in enumerate(boards,1):
 random.seed(index)
 im=Image.new('RGB',(1100,780),(178,184,184));d=ImageDraw.Draw(im)
 d.rounded_rectangle((26,22,1074,754),radius=8,fill=(105,114,117))
 d.rectangle((42,38,1058,738),fill=(242,243,235))
 for j in range(150):
  x=random.randrange(45,1050);y=random.randrange(40,732);d.line((x,y,min(x+random.randrange(20,170),1056),y+random.randrange(-2,3)),fill=(232,234,226),width=1)
 for row,line in enumerate(lines):
  color=(27,39,47) if row!=1 else (33,58,91)
  font=ImageFont.truetype(FONT,54 if row==0 else 58)
  # Small baseline offsets make these distinct handwriting-style fixtures.
  d.text((85+random.randrange(-4,5),65+row*98+random.randrange(-3,4)),line,fill=color,font=font,stroke_width=0)
 d.line((89,247,960,244),fill=(43,61,75),width=3)
 # A steel frame, marker and slight perspective/rotation, as a kitchen reference photograph.
 d.rounded_rectangle((900,707,1020,723),radius=5,fill=(36,44,48));d.rectangle((900,707,922,723),fill=(13,54,101))
 im=im.rotate([-1.2,.8,-.6][index-1],resample=Image.Resampling.BICUBIC,fillcolor=(178,184,184))
 im.save(f'public/whiteboards/menu-{index}.jpg',quality=89)
Image.new('RGB',(800,600),(241,242,239)).save('public/whiteboards/blank.jpg')
random.seed(41)
im=Image.new('RGB',(800,600),(238,239,234));d=ImageDraw.Draw(im)
for j in range(80):
 x=random.randrange(100,700);y=random.randrange(70,550)
 d.line([(x,y),(x+random.randrange(-50,50),y+random.randrange(-30,30)),(x+random.randrange(-90,90),y+random.randrange(-40,40))],fill=(75,83,89),width=4)
im=im.filter(ImageFilter.GaussianBlur(9));im.save('public/whiteboards/garbled.jpg',quality=70)
