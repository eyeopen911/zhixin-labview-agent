"""Style real FP heap and generated VI icons before the binary is serialized."""
import pathlib,xml.etree.ElementTree as E,re
from PIL import Image,ImageDraw,ImageFont

def install(m,enabled):
 if enabled:
  m.Composer.COLUMN_GAP=60
  m.Composer.COLUMN_MAX=860
 old=m.Composer.write
 def write(self,out_dir,base):
  result=old(self,out_dir,base)
  # Icons belong to the actual subVIs and appear in the real caller diagram.
  title=self.vi_name.split('_')[0];short={'HandleCommand':'CMD','ProcessTimeout':'TICK','UpdateDiagnostics':'DIAG','NormalizeTimeout':'TIME','EvaluateDisplay':'VIEW','ConfigurePanel':'INIT'}.get(title)
  if short:
   for suffix in ('_ICON.png','_icl8.png'):
    file=pathlib.Path(out_dir)/(base+suffix)
    if file.exists():
     im=Image.new('RGB',(32,32),'white');d=ImageDraw.Draw(im);d.rectangle((0,0,31,31),outline='#39495c');d.rectangle((1,1,30,8),fill='#366e95');font=ImageFont.truetype('DejaVuSansMono.ttf',10) if pathlib.Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf').exists() else ImageFont.load_default();d.text((2,13),short,font=font,fill='#172939');original=Image.open(file);im=im.quantize(palette=original) if original.mode=='P' else im.convert(original.mode);im.save(file)
  if enabled:polish(pathlib.Path(out_dir)/(base+'_FPHb.xml'))
  return result
 m.Composer.write=write

def polish(file):
 tree=E.parse(file);root=tree.getroot();pane=root.find('.//paneHierarchy');z=pane.find('zPlaneList')
 def rect(el):return list(map(int,re.findall(r'-?\d+',el.text)))
 def setrect(el,v):el.text='('+', '.join(map(str,v))+')'
 positions={'Samples':(110,35),'Values':(110,300),'Gain':(95,565),'Offset':(165,565),'IntervalMs':(235,565),'Limit':(305,565),'PeakAbs':(390,440),'Average':(390,300),'TickCount':(390,35),'ResetCount':(390,565),'Running':(450,565),'Start':(450,35),'Stop':(450,145),'Reset':(450,255),'Exit':(450,365)}
 for item in z:
  d=item.find('ddo')
  if d is None:continue
  text=d.find('./partsList/SL__arrayElement[@class="label"]/textRec/text')
  if text is None:continue
  name=text.text.strip('"');bounds=d.find('bounds');t,l,b,r=rect(bounds)
  if name.startswith('NI_'):
   d.find('objFlags').text=str(int(d.findtext('objFlags'))|8)
   continue
  y,x=positions.get(name,(310,565));setrect(bounds,[y,x,y+b-t,x+r-l])
 z.set('elements',str(len(z)));pane.find('bounds').text='(46, 0, 630, 840)'
 for p in pane.find('partsList'):
  if p.findtext('partID')=='28':p.find('bounds').text='(0, 0, 567, 823)';p.find('bgColor').text='00F2F4F7'
 tree.write(file,encoding='utf-8',xml_declaration=True)

