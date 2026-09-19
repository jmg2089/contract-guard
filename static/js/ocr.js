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

  /* 이미지 한 장 -> 텍스트 */
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
      const { data } = await worker.recognize(source);
      return data.text || "";
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
      // 2배로 키워 렌더한다. 원본 해상도 그대로면 OCR 정확도가 크게 떨어진다
      const viewport = page.getViewport({ scale: 2.0 });
      const canvas = document.createElement("canvas");
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
      parts.push(await imageToText(canvas, onProgress));
    }

    if (pdf.numPages > MAX_PAGES && onStatus) {
      onStatus(`${MAX_PAGES}쪽까지만 읽었습니다. 뒷부분은 직접 붙여넣어 주세요.`);
    }
    return parts.join("\n");
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

  return { imageToText, scannedPdfToText, tidy };
})();
