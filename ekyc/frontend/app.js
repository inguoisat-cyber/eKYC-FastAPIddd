'use strict';
const $ = (s) => document.querySelector(s);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PROMPT = {
  look_straight: 'Nhìn thẳng vào camera',
  turn_left_gentle: 'Nghiêng nhẹ mặt sang TRÁI 👈',
  turn_right_gentle: 'Nghiêng nhẹ mặt sang PHẢI 👉',
};

let sid = null;        // session id
let stream = null;     // một luồng camera dùng chung cho mặt trước + mặt sau (không xin/khởi động lại)
let facing = null;
let run = 0;           // token: tăng mỗi lần đổi màn hình để dừng vòng lặp cũ
let step = 0;

// ── tiện ích ─────────────────────────────────────────────────────────
async function post(path, body) {
  const opts = { method: 'POST' };
  if (body instanceof FormData) opts.body = body;
  else if (body) Object.assign(opts, { body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } });
  const r = await fetch('/api/kyc' + path, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(typeof d.detail === 'string' ? d.detail : `Lỗi máy chủ (${r.status})`), { status: r.status });
  return d;
}

function view(n, html) {
  run++;
  step = n;
  document.querySelectorAll('#bar i').forEach((el, i) => el.classList.toggle('on', i <= n));
  $('#app').innerHTML = html;
}

function stopCam() {
  stream?.getTracks().forEach((t) => t.stop());
  stream = facing = null;
}

async function attachCam(kind, video, w, h) {
  if (!stream || facing !== kind) {
    stopCam();
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: kind }, width: { ideal: w }, height: { ideal: h } }, audio: false,
    });
    facing = kind;
  }
  video.srcObject = stream;
  await video.play();
  video.parentElement.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`; // khung khớp đúng ảnh sẽ chụp
}

const cv = document.createElement('canvas'); // dùng lại 1 canvas, không tạo mới mỗi khung hình
function snap(video, maxW, mirror, quality) {
  const k = Math.min(1, maxW / video.videoWidth);
  cv.width = Math.round(video.videoWidth * k);
  cv.height = Math.round(video.videoHeight * k);
  const c = cv.getContext('2d');
  if (mirror) { c.translate(cv.width, 0); c.scale(-1, 1); }
  c.drawImage(video, 0, 0, cv.width, cv.height);
  return new Promise((res) => cv.toBlob(res, 'image/jpeg', quality));
}

function fail(e, retryLabel, retry) {
  const dead = [404, 410, 429].includes(e.status); // phiên hỏng/hết hạn/hết lượt thử: chỉ còn cách bắt đầu lại
  if (e.name === 'NotAllowedError' || e.name === 'NotFoundError') e = new Error('Không truy cập được camera. Hãy cấp quyền camera cho trình duyệt.');
  view(step, `<h2 class="err">Có lỗi xảy ra</h2><p class="err" id="e"></p>
    <div class="row"><button id="again"></button>${dead ? '' : '<button class="ghost" id="reset">Làm lại từ đầu</button>'}</div>`);
  $('#e').textContent = e.message;
  $('#again').textContent = dead ? 'Bắt đầu lại' : retryLabel;
  $('#again').onclick = dead ? () => location.reload() : retry;
  if (!dead) $('#reset').onclick = () => location.reload();
}

// ── 0. Đồng ý ────────────────────────────────────────────────────────
function consentStep() {
  view(0, `<h2>Đồng ý điều khoản</h2>
    <p>Để xác minh, hệ thống cần chụp <b>2 mặt CCCD</b> và <b>khuôn mặt</b> của bạn. Ảnh được mã hoá khi lưu trữ.</p>
    <button id="go">Đồng ý & bắt đầu</button><p class="err" id="e"></p>`);
  $('#go').onclick = async (ev) => {
    ev.target.disabled = true;
    try { sid = (await post('/session', { consent: true })).id; docStep('front'); }
    catch (e) { ev.target.disabled = false; $('#e').textContent = e.message; }
  };
}

// ── 1-2. Chụp giấy tờ (dùng chung cho mặt trước và mặt sau) ───────────
async function docStep(side) {
  const front = side === 'front';
  view(front ? 1 : 2, `<h2>Chụp mặt ${front ? 'trước' : 'sau'} giấy tờ</h2>
    <p class="muted">Đặt thẻ vừa khung, đủ sáng, không lóa, chữ và mã QR rõ nét.</p>
    <div class="cam"><video playsinline muted></video><div class="guide"></div></div>
    <p class="muted" id="msg"></p>
    <div class="row"><button id="shot">📸 Chụp</button><button class="ghost" id="redo" hidden>Chụp lại</button><button id="next" hidden>Dùng ảnh này</button></div>`);
  const [v, msg, shot, redo, next] = ['video', '#msg', '#shot', '#redo', '#next'].map($);
  try { await attachCam('environment', v, 1280, 720); } catch (e) { return fail(e, 'Thử lại camera', () => docStep(side)); }

  let upload = null;
  const toggle = (taken) => { shot.hidden = taken; redo.hidden = next.hidden = !taken; };
  shot.onclick = async () => {
    const blob = await snap(v, 1280, false, 0.9);
    v.pause();
    toggle(true);
    const fd = new FormData();
    fd.append('file', blob, `${side}.jpg`);
    msg.textContent = 'Đang tải ảnh lên…';
    // tải lên ngay trong lúc người dùng xem lại ảnh -> không phải chờ ở bước sau
    upload = post(`/document/${side}?session_id=${sid}`, fd).then(
      () => { msg.textContent = '✅ Đã tải lên. Ảnh có rõ nét không?'; },
      (e) => { msg.textContent = '❌ ' + e.message; return e; });
  };
  redo.onclick = async () => { redo.disabled = true; await upload; redo.disabled = false; v.play(); toggle(false); msg.textContent = ''; };
  next.onclick = async () => {
    const err = await upload;
    if (err) return err.status === 404 || err.status === 410 ? fail(err) : undefined;
    front ? docStep('back') : processDocs();
  };
}

// ── 3. Đọc giấy tờ (1 request) ───────────────────────────────────────
async function processDocs() {
  stopCam();
  view(2, `<h2>Đang đọc giấy tờ…</h2><div class="spin"></div><p class="muted">Thường chỉ mất vài giây.</p>`);
  try { livenessStep((await post(`/document/process?session_id=${sid}`)).info); }
  catch (e) { fail(e, 'Chụp lại giấy tờ', () => docStep('front')); }
}

// ── 4. Liveness + so khớp khuôn mặt ──────────────────────────────────
async function livenessStep(info) {
  view(3, `<h2>Xác thực khuôn mặt</h2><p class="muted" id="who"></p><p class="muted" id="doccheck"></p>
    <div class="cam"><video playsinline muted style="transform:scaleX(-1)"></video><div class="oval"></div><div class="tip">Đang khởi động camera…</div></div>
    <div id="res"></div>`);
  const token = run;
  const [v, oval, tip, doccheck] = ['video', '.oval', '.tip', '#doccheck'].map($);
  if (info) {
    const identity = [info.full_name, info.id_number].filter(Boolean).join(' · ');
    $('#who').textContent = identity
      ? `Đã đọc: ${identity}`
      : 'Đã quét giấy tờ nhưng chưa trích xuất được tên hoặc số định danh.';
  } else $('#who').textContent = 'Không đọc được thông tin QR/OCR trên thẻ — bạn vẫn có thể tiếp tục xác thực khuôn mặt.';
  if (info?.read_sources) {
    const sources = `${info.read_sources.qr ? 'QR ✓' : 'QR không đọc được'} · ${info.read_sources.ocr ? 'OCR ✓' : 'OCR không đọc được'}`;
    const check = info.cross_check;
    doccheck.textContent = check?.valid === false
      ? `${sources} — CẢNH BÁO: dữ liệu QR và OCR lệch ở ${Object.entries(check.matches || {}).filter(([, match]) => !match).map(([key]) => key).join(', ') || 'nguồn dữ liệu'}.`
      : `${sources}${check?.reason === 'one_source_missing' ? ' · Chưa thể đối chiếu đủ hai nguồn.' : ' · Đã đối chiếu.'}`;
    if (check?.valid === false) doccheck.classList.add('err');
  }

  let ch;
  try {
    // xin challenge và bật camera song song
    [ch] = await Promise.all([post(`/liveness/challenge?session_id=${sid}`), attachCam('user', v, 640, 480)]);
  } catch (e) { return fail(e, 'Thử lại', () => livenessStep(info)); }
  if (token !== run) return;
  tip.textContent = PROMPT[ch.type] || PROMPT.look_straight;
  await sleep(500);

  while (token === run) {
    if (document.hidden) { await sleep(500); continue; }
    const fd = new FormData();
    fd.append('session_id', sid);
    fd.append('image', await snap(v, 480, true, 0.8), 's.jpg'); // khung 480px đủ cho detect@320 và nhẹ hơn ~2x so với 640
    let r;
    try { r = await post('/liveness/verify', fd); }
    catch (e) { if (token === run) fail(e, 'Thử lại', () => livenessStep(info)); return; }
    if (token !== run) return;
    if (!r.done) { oval.style.borderColor = '#ff9800'; tip.textContent = r.message; await sleep(100); continue; }

    stopCam();
    oval.style.borderColor = r.success ? '#4caf50' : '#f44336';
    tip.textContent = r.success ? '✅ Hoàn tất' : '❌ Không khớp';
    $('#res').innerHTML = r.success
      ? `<div class="box ok"><h2 class="ok">🎉 Xác thực thành công</h2><p>✔️ Người thật (Liveness)</p>
         <p>✔️ Khớp khuôn mặt: <b id="sim"></b></p></div>`
      : `<div class="box err"><h2 class="err">❌ Xác thực thất bại</h2><p id="why"></p>
         <div class="row"><button id="retry">Thử lại selfie</button><button class="ghost" id="reset">Làm lại từ đầu</button></div></div>`;
    if (r.success) $('#sim').textContent = (r.similarity * 100).toFixed(1) + '%';
    else {
      $('#why').textContent = r.message;
      $('#retry').onclick = () => livenessStep(info);
      $('#reset').onclick = () => location.reload();
    }
    return;
  }
}

consentStep();
