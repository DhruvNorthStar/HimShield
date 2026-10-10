"""Self-contained image-coordinate navigation. No basemap, vector or georeferencing."""
import base64
from html import escape
import json

from src import config
from src.demo_map import ZONE_COLOURS


def html(png: bytes, district: str) -> str:
    # Only a PNG, public class names/colours and a district label cross this boundary.
    return TEMPLATE.replace("__TITLE__", escape(district)).replace("__PNG__", base64.b64encode(png).decode("ascii")).replace(
        "__COLOURS__", json.dumps(ZONE_COLOURS)).replace("__CLASSES__", json.dumps(config.RISK_ZONES))


TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{margin:0;font:14px system-ui,sans-serif;color:#172B4D;background:#FFFFFF}
header{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:10px;border-bottom:1px solid #D8E2EC}
button{background:#FFFFFF;color:#102A43;border:1px solid #526579;border-radius:5px;padding:9px 14px;cursor:pointer}
button:focus-visible,canvas:focus-visible{outline:3px solid #0F766E;outline-offset:2px}
canvas{display:block;width:100%;height:530px;background:#F5F7FA;touch-action:none;cursor:grab}
footer{padding:10px}p{margin:5px 0;line-height:1.5}
</style></head><body>
<header><strong>__TITLE__ · statewide RF district view</strong><span>Grid north ↑</span>
<button id="plus" aria-label="Zoom in">Zoom +</button><button id="minus" aria-label="Zoom out">Zoom −</button>
<button id="reset">Reset view</button></header>
<canvas id="map" tabindex="0" aria-label="District raster image. Arrow keys pan, plus or minus zoom, Home resets, Enter inspects the centre."></canvas>
<footer><p id="status" role="status" aria-live="polite">Drag to pan; zoom with buttons or the mouse wheel. Click a display cell to inspect its class.</p>
<p>Reduced raster image; no geographic coordinates or site-level scores. Gray is NoData.</p>
<p>Source: Survey of India, Government of India. Local academic display only.</p></footer>
<script>
'use strict';
const colours=__COLOURS__, classes=__CLASSES__, canvas=document.getElementById('map'), ctx=canvas.getContext('2d');
const image=new Image(), status=document.getElementById('status');
let scale=1, fit=1, x=0, y=0, drag=null, origin=null, moved=false, pixels=null;
function draw(){ctx.clearRect(0,0,canvas.width,canvas.height);ctx.imageSmoothingEnabled=false;ctx.drawImage(image,x,y,image.width*scale,image.height*scale);}
function reset(){canvas.width=Math.max(1,Math.round(canvas.getBoundingClientRect().width));canvas.height=530;
 fit=Math.min(canvas.width/image.width,canvas.height/image.height);scale=fit;
 x=(canvas.width-image.width*scale)/2;y=(canvas.height-image.height*scale)/2;draw();}
function zoom(factor){const next=Math.max(fit*0.5,Math.min(fit*16,scale*factor));
 const cx=canvas.width/2,cy=canvas.height/2;x=cx-(cx-x)*next/scale;y=cy-(cy-y)*next/scale;scale=next;draw();}
function position(event){const r=canvas.getBoundingClientRect();return {x:(event.clientX-r.left)*canvas.width/r.width,y:(event.clientY-r.top)*canvas.height/r.height};}
function inspect(p){const col=Math.floor((p.x-x)/scale),row=Math.floor((p.y-y)/scale);
 if(col<0||row<0||col>=image.width||row>=image.height){status.textContent='Outside the preview.';return;}
 const i=(row*image.width+col)*4;if(!pixels[i+3]){status.textContent='Outside the district mask; no class assigned.';return;}
 const hex='#'+[pixels[i],pixels[i+1],pixels[i+2]].map(v=>v.toString(16).padStart(2,'0')).join('');
 const zone=colours.findIndex(c=>c.toLowerCase()===hex);
 status.textContent=zone<0?'NoData: unscored source cell, not low susceptibility.':
  'Nearest sampled display cell: '+classes[zone]+'. Reduced preview; not a site-level assessment.';}
canvas.addEventListener('pointerdown',e=>{drag=position(e);origin=drag;moved=false;canvas.setPointerCapture(e.pointerId);});
canvas.addEventListener('pointermove',e=>{if(!drag)return;const p=position(e),dx=p.x-drag.x,dy=p.y-drag.y;
 if(Math.abs(p.x-origin.x)+Math.abs(p.y-origin.y)>3)moved=true;x+=dx;y+=dy;drag=p;draw();});
canvas.addEventListener('pointerup',e=>{if(!moved)inspect(position(e));drag=null;});
canvas.addEventListener('pointercancel',()=>{drag=null;});
canvas.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY<0?1.2:1/1.2);},{passive:false});
canvas.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='=')zoom(1.2);else if(e.key==='-')zoom(1/1.2);
 else if(e.key==='Home')reset();else if(e.key==='Enter')inspect({x:canvas.width/2,y:canvas.height/2});
 else if(e.key==='ArrowLeft')x+=30;else if(e.key==='ArrowRight')x-=30;
 else if(e.key==='ArrowUp')y+=30;else if(e.key==='ArrowDown')y-=30;else return;e.preventDefault();draw();});
document.getElementById('plus').onclick=()=>zoom(1.2);document.getElementById('minus').onclick=()=>zoom(1/1.2);
document.getElementById('reset').onclick=reset;window.addEventListener('resize',()=>{if(image.complete&&pixels)reset();});
image.onload=()=>{const buffer=document.createElement('canvas');buffer.width=image.width;buffer.height=image.height;
 const raw=buffer.getContext('2d');raw.drawImage(image,0,0);pixels=raw.getImageData(0,0,image.width,image.height).data;reset();};
image.src='data:image/png;base64,__PNG__';
</script></body></html>"""
