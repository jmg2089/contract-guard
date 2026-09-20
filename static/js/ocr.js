/* 브라우저에서 돌아가는 OCR — 스캔본·사진·캡처 화면 지원.
 *
 * 왜 서버가 아니라 브라우저인가:
 *   1) Render 무료 인스턴스는 apt 설치가 막혀 OCR 엔진을 깔 수 없다
 *   2) EasyOCR·PaddleOCR 계열은 torch 800MB 이상이라 512MB 메모리에 안 들어간다
 *   3) 외부 OCR API를 쓰면 "외부 API 호출 0회"라는 우리 설계가 깨진다
 *
 * 브라우저에서 돌리면 셋 다 피한다. 그리고 얻는 게 하나 더 있다.
 *   계약서 이미지가 서버로 전송되지 않는다. 사용자 기기 안에서만 처리된다.
 *   근로계약서는 이름·주소·급여가 들어 있는 민감 문서다. 이게 작은 장점이 아니다.
 *
 * 정확도 한계가 있으므로 결과를 바로 분석에 넘기지 않는다.
 * 입력창에 채워 넣고 사용자가 확인·수정한 뒤 직접 [검사하기]를 누르게 한다.
 */

const OCR = (() => {
  const TESSERACT_CDN = "https://cdn.jsdelivr.net/npm/tesseract.js@6/dist/tesseract.min.js";
  const PDFJS_CDN = "https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.min.js";
  const PDFJS_WORKER = "https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js";
  const MAX_PAGES = 5; // 계약서는 보통 1~3쪽. 무한정 돌면 사용자가 기다리다 나간다

  let loaded = {};

  function loadScript(src) {
    if (loaded[src]) return loaded[src];
    loaded[src] = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error(`스크립트를 불러오지 못했습니다: ${src}`));
      document.head.appendChild(s);
    });
    return loaded[src];
  }

  /* ── 전처리 ────────────────────────────────────────────────────────────
   *
   * 여기서 인식률이 갈린다. 전역 기준으로 대비를 미는 방식(g < 140 ? ... )을
   * 처음에 썼는데, 실제 휴대폰 사진에서 오히려 원본보다 나빠졌다.
   *
   * 실측: 인쇄물을 휴대폰으로 찍은 1쪽짜리 문서 (tesseract 5 / kor)
   *
   *     원본 그대로        키워드 2/6
   *     전역 대비          키워드 0/6   <- 손대서 더 나빠졌다
   *     국소 이진화        키워드 4/6
   *
   * 이유는 분명하다. 사진에는 조명 얼룩이 있다. 한쪽은 밝고 한쪽은 그늘진다.
   * 전역 기준 하나로 자르면 밝은 쪽은 글자까지 하얗게 날아가고, 어두운 쪽은
   * 배경까지 까맣게 뭉갠다. 스캔본에는 통하지만 사진에는 안 통하는 방식이었다.
   *
   * 그래서 국소 이진화로 바꿨다. 각 픽셀을 '그 주변의 평균'과 비교한다.
   * 밝은 구역에서는 기준이 높게, 그늘진 구역에서는 낮게 잡히므로 조명 얼룩이
   * 저절로 흡수된다. 적분영상(integral image)을 쓰면 반경과 무관하게
   * 픽셀당 연산이 일정하다 — 2400px 이미지도 브라우저에서 수십 ms 안에 끝난다.
   */

  /* 캔버스를 국소 이진화한다. 원본 캔버스를 그대로 고친다.
   *
   * 메모리에 주의해야 한다. 이 코드는 사용자 휴대폰에서 돈다.
   * 명암 배열은 0~255 이므로 Uint8Array 로 충분하다(Float64 로 잡으면 8배를 쓴다).
   * 적분영상만은 누적합이 수억까지 올라가 Float64 가 필요하다. */
  function binarize(canvas) {
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    const img = ctx.getImageData(0, 0, w, h);
    const d = img.data;

    // 1) 흑백으로
    const g = new Uint8Array(w * h);
    for (let i = 0, p = 0; i < d.length; i += 4, p++) {
      g[p] = (0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]) | 0;
    }

    // 2) 적분영상 — (w+1) x (h+1), 누적합
    const ii = new Float64Array((w + 1) * (h + 1));
    for (let y = 0; y < h; y++) {
      let rowSum = 0;
      for (let x = 0; x < w; x++) {
        rowSum += g[y * w + x];
        ii[(y + 1) * (w + 1) + (x + 1)] = ii[y * (w + 1) + (x + 1)] + rowSum;
      }
    }

    // 3) 반경은 글자 크기에 맞춰 잡는다. 너무 작으면 글자 속이 파이고,
    //    너무 크면 전역 기준과 다를 바 없어진다. 짧은 변의 약 4.5%가 안정적이다.
    const r = Math.max(8, Math.round(Math.min(w, h) * 0.045 / 2));
    const C = 10; // 주변 평균보다 이만큼 더 어두워야 글자로 본다 (옅은 얼룩 무시)

    for (let y = 0; y < h; y++) {
      const y0 = Math.max(0, y - r);
      const y1 = Math.min(h - 1, y + r);
      for (let x = 0; x < w; x++) {
        const x0 = Math.max(0, x - r);
        const x1 = Math.min(w - 1, x + r);
        const area = (y1 - y0 + 1) * (x1 - x0 + 1);
        const sum =
          ii[(y1 + 1) * (w + 1) + (x1 + 1)] -
          ii[y0 * (w + 1) + (x1 + 1)] -
          ii[(y1 + 1) * (w + 1) + x0] +
          ii[y0 * (w + 1) + x0];
        const mean = sum / area;
        const p = y * w + x;
        const v = g[p] < mean - C ? 0 : 255;
        const i = p * 4;
        d[i] = d[i + 1] = d[i + 2] = v;
        d[i + 3] = 255;
      }
    }

    ctx.putImageData(img, 0, 0);
    return canvas;
  }

  /* 파일(사진·캡처) -> 전처리된 캔버스.
   *
   * 가로를 2200px 부근으로 맞춘다. 작으면 키우고, 크면 줄인다.
   * 키우는 이유: 글자가 작으면 자모가 뭉개져 이진화로도 못 살린다.
   * 줄이는 이유: 요즘 휴대폰 사진은 4000px 이 넘는다. 그대로 두면 인식이 느려지고
   *              메모리도 크게 먹는데, 문서 OCR은 2200px 이상에서 정확도가 거의 안 는다. */
  const WORK_WIDTH = 2200;

  async function preprocess(file) {
    const bitmap = await createImageBitmap(file);
    const scale = WORK_WIDTH / bitmap.width;
    const w = Math.round(bitmap.width * scale);
    const h = Math.round(bitmap.height * scale);

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(bitmap, 0, 0, w, h);
    return binarize(canvas);
  }

  /* 이미 그려진 캔버스(PDF 렌더 결과)에도 같은 처리를 한다 */
  function enhance(canvas) {
    return binarize(canvas);
  }

  /* 읽어낸 글자가 쓸 만한지 즉시 판별한다.
     서버도 검사하지만, 사용자가 [검사하기]를 누르기 전에 알려주는 편이 친절하다 */
  function quality(text) {
    const letters = (text.match(/[가-힣a-zA-Z]/g) || []).length;
    const hangul = (text.match(/[가-힣]/g) || []).length;
    const ratio = letters ? hangul / letters : 0;
    const terms = ["근로", "임금", "계약", "근무", "시간", "지급", "회사", "퇴직"]
      .filter((t) => text.includes(t)).length;
    // 레이아웃 모드를 고를 때 쓸 단일 점수. 서버의 core/pdftext.py 와 같은 기준이다.
    const score =
      ratio * 0.5 +
      Math.min(terms / 6, 1) * 0.35 +
      Math.min(letters / 300, 1) * 0.15;
    return { ratio, terms, letters, score, good: ratio >= 0.5 && terms >= 2 };
  }

  /* 이미지 한 장 -> 텍스트.
   *
   * 레이아웃 모드를 하나로 고정하지 않는다. PDF 추출에서 엔진 하나를 믿지 않은 것과
   * 같은 이유다. 계약서처럼 본문이 한 덩어리인 문서는 모드 6(단일 블록)이 안정적이지만,
   * 표·도장·로고가 섞이거나 단이 나뉜 문서에서는 모드 3(자동 분석)이 크게 낫다.
   * 실측에서 같은 사진이 모드 6은 키워드 2/6, 모드 3은 4/6 이었다.
   *
   * 그래서 6으로 먼저 읽고, 결과가 시원찮을 때만 3으로 한 번 더 읽는다.
   * 항상 두 번 돌리면 대기 시간이 두 배가 되므로, 실패했을 때만 비용을 낸다.
   * 워커는 하나를 재사용한다 — 워커 생성이 인식보다 비싸다.
   */
  async function imageToText(source, onProgress) {
    await loadScript(TESSERACT_CDN);
    const worker = await Tesseract.createWorker("kor+eng", 1, {
      logger: (m) => {
        if (m.status === "recognizing text" && onProgress) {
          onProgress(m.progress);
        }
      },
    });
    try {
      const read = async (psm) => {
        await worker.setParameters({ tessedit_pageseg_mode: psm });
        const { data } = await worker.recognize(source);
        return data.text || "";
      };

      const first = await read("6");
      const q1 = quality(first);
      if (q1.good) return first;

      const second = await read("3");
      const q2 = quality(second);
      // 점수가 같으면 먼저 읽은 쪽을 남긴다. 근거 없이 바꾸지 않는다.
      return q2.score > q1.score ? second : first;
    } finally {
      await worker.terminate();
    }
  }

  /* 스캔 PDF -> 페이지를 이미지로 렌더한 뒤 OCR */
  async function scannedPdfToText(file, onStatus, onProgress) {
    await loadScript(PDFJS_CDN);
    pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;

    const buf = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
    const pageCount = Math.min(pdf.numPages, MAX_PAGES);
    const parts = [];

    for (let i = 1; i <= pageCount; i++) {
      if (onStatus) onStatus(`${i}/${pageCount}쪽 글자를 읽는 중입니다...`);
      const page = await pdf.getPage(i);
      // A4 기준 가로 2400px 안팎이 되도록 배율을 잡는다.
      // 원본 해상도 그대로 렌더하면 한글 자모가 뭉개져 인식률이 크게 떨어진다.
      const base = page.getViewport({ scale: 1.0 });
      const scale = Math.min(4.0, Math.max(1.5, WORK_WIDTH / base.width));
      const viewport = page.getViewport({ scale });
      const canvas = document.createElement("canvas");
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      await page.render({ canvasContext: ctx, viewport }).promise;
      parts.push(await imageToText(enhance(canvas), onProgress));
    }

    if (pdf.numPages > MAX_PAGES && onStatus) {
      onStatus(`${MAX_PAGES}쪽까지만 읽었습니다. 뒷부분은 직접 붙여넣어 주세요.`);
    }
    return parts.join("\n");
  }

  /* ── 사진·스캔본도 가린 그림을 보여준다 ───────────────────────────────
   *
   * 글자가 들어 있는 PDF는 서버가 좌표를 알고 있어 검은 박스를 덮을 수 있다.
   * 그런데 휴대폰으로 찍은 사진이나 카카오톡으로 받은 PDF는 글자가 이미지라
   * 서버가 좌표를 모른다. 그동안 이런 파일은 미리보기 없이 글자만 채워 줬다.
   *
   * 사용자 입장에서는 이쪽이 더 불안하다. 사진에는 이름도 주민번호도 그대로
   * 찍혀 있는데 가려진 것을 볼 수가 없기 때문이다.
   *
   * 그래서 OCR 이 돌려주는 단어 좌표를 받아 브라우저에서 직접 덮는다.
   * 좌표를 못 받는 경우(엔진 버전 차이 등)에는 그림만 보여주고 그 사실을
   * 그대로 알린다. 가렸다고 거짓말하지 않는다.
   */
  async function readWithBoxes(canvas, onProgress) {
    await loadScript(TESSERACT_CDN);
    const worker = await Tesseract.createWorker("kor+eng", 1, {
      logger: (m) => {
        if (m.status === "recognizing text" && onProgress) onProgress(m.progress);
      },
    });
    try {
      await worker.setParameters({ tessedit_pageseg_mode: "6" });
      // blocks:true 를 줘야 단어 좌표가 따라온다. 기본값은 글자만 돌려준다.
      const { data } = await worker.recognize(canvas, {}, { text: true, blocks: true });
      const words = [];
      const walk = (node) => {
        if (!node || typeof node !== "object") return;
        if (Array.isArray(node)) return node.forEach(walk);
        if (node.text !== undefined && node.bbox && node.words === undefined) {
          words.push({ text: node.text, bbox: node.bbox });
        }
        ["blocks", "paragraphs", "lines", "words"].forEach((k) => {
          if (node[k]) walk(node[k]);
        });
      };
      try { walk(data.blocks); } catch (e) { /* 좌표 없이 진행 */ }
      return { text: data.text || "", words };
    } finally {
      await worker.terminate();
    }
  }

  /* 민감정보가 들어 있는 단어의 좌표를 찾아 캔버스에 검은 박스를 덮는다.
     판정 기준은 mask.js 와 같다. 두 곳이 어긋나면 안 된다. */
  function redactCanvas(canvas, words) {
    if (!words || !words.length || typeof Mask === "undefined") return 0;

    // 줄 단위로 묶어야 '성명 : 홍길동' 처럼 라벨과 값이 떨어져 있어도 잡힌다
    const rows = {};
    words.forEach((w) => {
      const key = Math.round((w.bbox.y0 + w.bbox.y1) / 2 / 12);
      (rows[key] = rows[key] || []).push(w);
    });

    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#111";
    let count = 0;

    Object.values(rows).forEach((row) => {
      row.sort((a, b) => a.bbox.x0 - b.bbox.x0);
      const line = row.map((w) => w.text).join(" ");
      const masked = Mask.apply(line);
      if (!Object.keys(masked.counts).length) return;

      // 어느 단어가 가려졌는지 알아내려면 단어별로 다시 확인한다.
      // 라벨(성명, 연락처 등) 다음 단어들이 값이므로 그 뒤를 덮는다.
      let hitLabel = false;
      row.forEach((w) => {
        const single = Mask.apply(w.text);
        const isValue = Object.keys(single.counts).length > 0;
        if (/^(성\s*명|이\s*름|주\s*소|연\s*락\s*처|생\s*년\s*월\s*일|주민등록번호|사업체명|대\s*표\s*자|이\s*메\s*일|급여계좌|계좌번호)/.test(w.text)) {
          hitLabel = true;
          return;
        }
        if (isValue || (hitLabel && !/^[:：]$/.test(w.text))) {
          const b = w.bbox;
          ctx.fillRect(b.x0 - 2, b.y0 - 2, b.x1 - b.x0 + 4, b.y1 - b.y0 + 4);
          count += 1;
        }
      });
    });
    return count;
  }

  /* 파일(사진·스캔 PDF) -> [{ image, boxes }] 미리보기용 그림 목록 + 읽어낸 글자 */
  async function maskedPreview(file, onStatus, onProgress) {
    const pages = [];
    let allText = [];
    let boxTotal = 0;
    let canvases = [];

    if (file.type.startsWith("image/")) {
      canvases = [await preprocess(file)];
    } else {
      await loadScript(PDFJS_CDN);
      pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
      const pdf = await pdfjsLib.getDocument({ data: await file.arrayBuffer() }).promise;
      const n = Math.min(pdf.numPages, MAX_PAGES);
      for (let i = 1; i <= n; i++) {
        if (onStatus) onStatus(`${i}/${n}쪽을 읽는 중입니다...`);
        const page = await pdf.getPage(i);
        const base = page.getViewport({ scale: 1.0 });
        const scale = Math.min(4.0, Math.max(1.5, WORK_WIDTH / base.width));
        const viewport = page.getViewport({ scale });
        const canvas = document.createElement("canvas");
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        await page.render({ canvasContext: ctx, viewport }).promise;
        canvases.push(enhance(canvas));
      }
    }

    for (let i = 0; i < canvases.length; i++) {
      const canvas = canvases[i];
      const { text, words } = await readWithBoxes(canvas, onProgress);
      allText.push(text);
      boxTotal += redactCanvas(canvas, words);
      pages.push({ page: i + 1, image: canvas.toDataURL("image/png") });
    }

    return { pages, text: tidy(allText.join("\n")), boxes: boxTotal };
  }

  /* 읽어낸 글자를 정리한다. OCR 결과는 줄바꿈과 공백이 지저분하다 */
  function tidy(text) {
    return text
      .replace(/\r/g, "")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .split("\n")
      .map((l) => l.trim())
      .join("\n")
      .trim();
  }

  return { imageToText, scannedPdfToText, maskedPreview, tidy, preprocess, enhance, quality };
})();
