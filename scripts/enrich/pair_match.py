#!/usr/bin/env python3
"""
pair_match — match ONE pano annotation's (full-res) crop against ONE specific photo,
to calibrate verification: how many inliers does a TRUE positive get vs the
false-positive ~8-16? Reports raw matches, F-inliers, H-inliers, ratio; saves a viz.

  scripts/enrich/.venv/bin/python scripts/enrich/pair_match.py \
     --ann 67c6c4b9 --photo 4b8cac8a
"""
import argparse, base64, csv, glob, io, json, math, os, urllib.request
import numpy as np, cv2, torch, kornia.feature as KF
from PIL import Image
csv.field_size_limit(10**9)
HERE=os.path.dirname(os.path.abspath(__file__)); D=os.path.expanduser("~/hggg")
MAXKP=2048


def fc(p): return sorted(glob.glob(os.path.join(D,p+"*.csv")))[-1]
def wkt(g):
    if g and g.upper().startswith("POINT"):
        lo,la=g[g.index("(")+1:g.index(")")].split(); return float(lo),float(la)
    return None
def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"hillview-enrich/0.2"})
    return Image.open(io.BytesIO(urllib.request.urlopen(req,timeout=60).read())).convert("RGB")
def resz(pil,ms):
    w,h=pil.size; s=min(1.0,ms/max(w,h))
    return pil.resize((max(1,int(w*s)),max(1,int(h*s)))) if s<1 else pil
def dzi_region(pyr,nx0,ny0,nx1,ny1):
    base=pyr["tiles_url"].rstrip("/"); fmt=pyr.get("format","webp")
    TS,OV=int(pyr["tile_size"]),int(pyr["overlap"]); W,H=int(pyr["width"]),int(pyr["height"])
    lvl=math.ceil(math.log2(max(W,H)))
    px0,px1=sorted((max(0,int(nx0*W)),min(W,int(nx1*W)))); py0,py1=sorted((max(0,int(ny0*H)),min(H,int(ny1*H))))
    c0,c1,r0,r1=px0//TS,(px1-1)//TS,py0//TS,(py1-1)//TS; ox,oy=c0*TS,r0*TS
    canvas=Image.new("RGB",((c1-c0+1)*TS+OV+1,(r1-r0+1)*TS+OV+1))
    for c in range(c0,c1+1):
        for r in range(r0,r1+1):
            try: t=fetch(f"{base}/{lvl}/{c}_{r}.{fmt}")
            except Exception: continue
            canvas.paste(t,(c*TS-(OV if c>0 else 0)-ox, r*TS-(OV if r>0 else 0)-oy))
    return canvas.crop((px0-ox,py0-oy,px1-ox,py1-oy))


def load_photo(pid):
    for r in csv.DictReader(open(fc("photos"))):
        if r["id"].startswith(pid):
            s=json.loads(r["sizes"]); fe=s.get("full") or {}
            return {"id":r["id"],"ll":wkt(r.get("geometry")),"full":fe.get("url"),"pyr":fe.get("pyramid"),
                    "w":int(r["width"]),"h":int(r["height"]),
                    "brg":float(r["compass_angle"]) if r.get("compass_angle") else None}
    raise SystemExit(f"photo {pid} not found")


def load_ann(aid):
    for r in csv.DictReader(open(fc("photo_annotations"))):
        if r["id"].startswith(aid):
            g=(json.loads(r["target"]).get("selector") or {}).get("geometry") or {}
            return {"photo_id":r["photo_id"],"body":r.get("body",""),
                    "rect":(float(g["x"]),float(g["y"]),float(g.get("w",0)),float(g.get("h",0)))}
    raise SystemExit("ann not found")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ann",default="67c6c4b9")
    ap.add_argument("--photo",required=True)
    ap.add_argument("--qmax",type=int,default=2048); ap.add_argument("--tmax",type=int,default=2048)
    a=ap.parse_args()
    ann=load_ann(a.ann); pano=load_photo(ann["photo_id"]); tgt=load_photo(a.photo)

    disk=KF.DISK.from_pretrained("depth").eval(); lg=KF.LightGlue("disk").eval()
    def extract(pil,ms):
        arr=np.asarray(resz(pil,ms))
        t=torch.from_numpy(arr.astype("float32")/255).permute(2,0,1)[None]
        with torch.inference_mode(): f=disk(t,MAXKP,pad_if_not_divisible=True)[0]
        return arr,f.keypoints,f.descriptors,torch.tensor([t.shape[-1],t.shape[-2]],dtype=torch.float32)
    # pano crop (full-res via pyramid)
    x,y,ww,hh=ann["rect"]; mg=0.10
    rect=(x-mg*ww,y-mg*hh,x+ww+mg*ww,y+hh+mg*hh)
    crop=dzi_region(pano["pyr"],*rect) if pano.get("pyr") else fetch(pano["full"]).crop(
        (int(rect[0]*pano["w"]),int(rect[1]*pano["h"]),int(rect[2]*pano["w"]),int(rect[3]*pano["h"])))
    tp=dzi_region(tgt["pyr"],0,0,1,1) if (tgt.get("pyr") and tgt["w"]>8200) else fetch(tgt["full"])
    f0=extract(crop,a.qmax); f1=extract(tp,a.tmax)
    inp={"image0":{"keypoints":f0[1][None],"descriptors":f0[2][None],"image_size":f0[3][None]},
         "image1":{"keypoints":f1[1][None],"descriptors":f1[2][None],"image_size":f1[3][None]}}
    with torch.inference_mode(): mm=lg(inp)["matches"][0].cpu().numpy()
    raw=len(mm); fin=hin=0; fmask=None
    if raw>=8:
        p0=f0[1].cpu().numpy()[mm[:,0]]; p1=f1[1].cpu().numpy()[mm[:,1]]
        F,fmask=cv2.findFundamentalMat(p0,p1,cv2.FM_RANSAC,3.0,0.99)
        fin=int(fmask.sum()) if fmask is not None else 0
        H,hmask=cv2.findHomography(p0,p1,cv2.RANSAC,5.0)
        hin=int(hmask.sum()) if hmask is not None else 0
    print(f"\nann {a.ann} ({ann['body'][:30]})  x  photo {a.photo} ({tgt['id'][:8]})")
    print(f"  crop {crop.size}  target {tp.size}  kp {f0[1].shape[0]}/{f1[1].shape[0]}")
    print(f"  raw matches: {raw}   F-inliers: {fin} ({100*fin//max(1,raw)}%)   H-inliers: {hin} ({100*hin//max(1,raw)}%)")
    # viz: side-by-side, thick green inlier (F) lines
    r0=np.asarray(resz(crop,a.qmax)); r1=np.asarray(resz(tp,a.tmax))
    h=max(r0.shape[0],r1.shape[0]); cv=np.zeros((h,r0.shape[1]+r1.shape[1],3),"uint8")
    cv[:r0.shape[0],:r0.shape[1]]=r0; cv[:r1.shape[0],r0.shape[1]:]=r1
    bg=cv2.cvtColor(cv,cv2.COLOR_RGB2BGR); off=r0.shape[1]
    k0=f0[1].cpu().numpy(); k1=f1[1].cpu().numpy()
    for j,(i0,i1) in enumerate(mm):
        if fmask is not None and not fmask[j]: continue
        cv2.line(bg,(int(k0[i0][0]),int(k0[i0][1])),(int(k1[i1][0])+off,int(k1[i1][1])),(0,220,0),2)
    out=os.path.join(HERE,f"pair_{a.ann[:8]}_{a.photo[:8]}.jpg")
    Image.fromarray(cv2.cvtColor(bg,cv2.COLOR_BGR2RGB)).save(out,"JPEG",quality=85)
    print(f"  viz: {out}")


if __name__=="__main__":
    main()
