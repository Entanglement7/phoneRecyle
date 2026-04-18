const fs = require('fs');
const zlib = require('zlib');

// CRC32
const crcTable = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
  return c;
});
const crc32 = buf => {
  let c = -1;
  for (const b of buf) c = (c >>> 8) ^ crcTable[(c ^ b) & 0xff];
  return (c ^ -1) >>> 0;
};

function makeChunk(type, data) {
  const t = Buffer.from(type);
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const crcBuf = Buffer.alloc(4); crcBuf.writeUInt32BE(crc32(Buffer.concat([t, data])));
  return Buffer.concat([len, t, data, crcBuf]);
}

function createPNG(W, H, draw) {
  const pixels = new Uint8Array(W * H * 4); // RGBA, init transparent
  draw(pixels, W, H);

  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(W, 0); ihdr.writeUInt32BE(H, 4);
  ihdr[8] = 8; ihdr[9] = 6; // RGBA

  const rows = Buffer.alloc(H * (W * 4 + 1));
  for (let y = 0; y < H; y++) {
    rows[y * (W * 4 + 1)] = 0;
    for (let x = 0; x < W; x++) {
      const src = (y * W + x) * 4, dst = y * (W * 4 + 1) + 1 + x * 4;
      rows[dst] = pixels[src]; rows[dst+1] = pixels[src+1];
      rows[dst+2] = pixels[src+2]; rows[dst+3] = pixels[src+3];
    }
  }

  return Buffer.concat([
    Buffer.from([137,80,78,71,13,10,26,10]),
    makeChunk('IHDR', ihdr),
    makeChunk('IDAT', zlib.deflateSync(rows)),
    makeChunk('IEND', Buffer.alloc(0))
  ]);
}

function setPixel(p, W, x, y, r, g, b, a = 255) {
  if (x < 0 || x >= W || y < 0 || y >= W) return;
  const i = (y * W + x) * 4;
  if (p[i+3] < a) { p[i]=r; p[i+1]=g; p[i+2]=b; p[i+3]=a; }
}

function drawLine(p, W, x1, y1, x2, y2, r, g, b, t = 1.8) {
  const dx = x2-x1, dy = y2-y1, len = Math.hypot(dx, dy);
  const steps = Math.ceil(len * 3);
  for (let i = 0; i <= steps; i++) {
    const px = x1 + dx*i/steps, py = y1 + dy*i/steps;
    for (let cy = Math.floor(py-t-1); cy <= Math.ceil(py+t+1); cy++)
      for (let cx = Math.floor(px-t-1); cx <= Math.ceil(px+t+1); cx++) {
        const d = Math.hypot(cx-px, cy-py);
        const a = Math.round(Math.max(0, Math.min(1, t+0.5-d)) * 255);
        if (a > 0) setPixel(p, W, cx, cy, r, g, b, a);
      }
  }
}

function drawCircle(p, W, cx, cy, radius, r, g, b, t = 1.8) {
  const steps = Math.ceil(radius * 2 * Math.PI * 3);
  for (let i = 0; i <= steps; i++) {
    const angle = 2 * Math.PI * i / steps;
    const px = cx + Math.cos(angle)*radius, py = cy + Math.sin(angle)*radius;
    for (let oy = Math.floor(py-t-1); oy <= Math.ceil(py+t+1); oy++)
      for (let ox = Math.floor(px-t-1); ox <= Math.ceil(px+t+1); ox++) {
        const d = Math.hypot(ox-px, oy-py);
        const a = Math.round(Math.max(0, Math.min(1, t+0.5-d)) * 255);
        if (a > 0) setPixel(p, W, ox, oy, r, g, b, a);
      }
  }
}

const GRAY = [153, 153, 153];
const BLUE = [26, 86, 219];

const icons = {
  // 首页 - 房子形状
  home: (col) => (p, W) => {
    const [r,g,b] = col, s = W/24;
    // 屋顶
    drawLine(p,W, 3*s,10*s, 12*s,2*s, r,g,b);
    drawLine(p,W, 12*s,2*s, 21*s,10*s, r,g,b);
    // 左墙 + 右墙
    drawLine(p,W, 3*s,10*s, 3*s,22*s, r,g,b);
    drawLine(p,W, 21*s,10*s, 21*s,22*s, r,g,b);
    // 底边
    drawLine(p,W, 3*s,22*s, 21*s,22*s, r,g,b);
    // 门
    drawLine(p,W, 9*s,22*s, 9*s,15*s, r,g,b);
    drawLine(p,W, 9*s,15*s, 15*s,15*s, r,g,b);
    drawLine(p,W, 15*s,15*s, 15*s,22*s, r,g,b);
  },
  // 估值记录 - 文档
  record: (col) => (p, W) => {
    const [r,g,b] = col, s = W/24;
    drawLine(p,W, 5*s,2*s, 19*s,2*s, r,g,b);
    drawLine(p,W, 19*s,2*s, 19*s,22*s, r,g,b);
    drawLine(p,W, 19*s,22*s, 5*s,22*s, r,g,b);
    drawLine(p,W, 5*s,22*s, 5*s,2*s, r,g,b);
    drawLine(p,W, 8*s,8*s, 16*s,8*s, r,g,b);
    drawLine(p,W, 8*s,12*s, 16*s,12*s, r,g,b);
    drawLine(p,W, 8*s,16*s, 13*s,16*s, r,g,b);
  },
  // 服务咨询 - 聊天气泡
  service: (col) => (p, W) => {
    const [r,g,b] = col, s = W/24;
    drawLine(p,W, 3*s,3*s, 21*s,3*s, r,g,b);
    drawLine(p,W, 21*s,3*s, 21*s,16*s, r,g,b);
    drawLine(p,W, 21*s,16*s, 8*s,16*s, r,g,b);
    drawLine(p,W, 8*s,16*s, 3*s,21*s, r,g,b);
    drawLine(p,W, 3*s,21*s, 3*s,3*s, r,g,b);
    // 点
    setPixel(p,W, Math.round(8*s), Math.round(9.5*s), r,g,b);
    setPixel(p,W, Math.round(12*s), Math.round(9.5*s), r,g,b);
    setPixel(p,W, Math.round(16*s), Math.round(9.5*s), r,g,b);
  },
  // 个人中心 - 人物
  profile: (col) => (p, W) => {
    const [r,g,b] = col, s = W/24;
    drawCircle(p,W, 12*s, 8*s, 4*s, r,g,b);
    // 身体弧线（分段折线模拟弧形）
    const segs = 20;
    for (let i = 0; i < segs; i++) {
      const t1 = i/segs, t2 = (i+1)/segs;
      const a1 = Math.PI + t1*Math.PI, a2 = Math.PI + t2*Math.PI;
      drawLine(p,W,
        12*s + Math.cos(a1)*8*s, 20*s + Math.sin(a1)*4*s,
        12*s + Math.cos(a2)*8*s, 20*s + Math.sin(a2)*4*s,
        r,g,b
      );
    }
  }
};

const W = 54;
const dir = 'C:/Users/15091/Documents/HBuilderProjects/phoneRecyle/static/tabbar/';

for (const [name, fn] of Object.entries(icons)) {
  fs.writeFileSync(dir + name + '.png', createPNG(W, W, fn(GRAY)));
  fs.writeFileSync(dir + name + '-active.png', createPNG(W, W, fn(BLUE)));
  console.log(`✓ ${name}.png`);
}
console.log('Done!');
