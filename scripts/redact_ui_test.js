/* 확대 모달 DOM 테스트 (jsdom)
 *
 * 왜 이 테스트가 필요한가.
 *
 * 이 화면의 최악은 "가린 줄 알았는데 안 가려진" 상태다. 확대 창을 만들 때
 * 캔버스를 복사해서 띄우면 칠한 내용을 되돌려 맞춰야 하고, 그 동기화가 한 번
 * 어긋나면 사용자는 가렸다고 믿은 채 계약서를 내보낸다.
 *
 * 그래서 redact.js 는 복사하지 않고 캔버스를 통째로 옮긴다. 이 테스트는
 * 그 약속이 실제로 지켜지는지 — 열 때 옮겨지고, 닫을 때 같은 캔버스가
 * 제자리로 돌아오며, 칠한 칸 수가 그대로인지 — 를 DOM 수준에서 확인한다.
 *
 * 실행: node scripts/redact_ui_test.js
 */

const fs = require("fs");
const path = require("path");
const { JSDOM } = require("/home/claude/node_modules/jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "static", "js", "redact.js"), "utf8"
);

const dom = new JSDOM(
  `<!doctype html><body>
     <div id="preview">
       <figure><img src="x.png" alt=""></figure>
     </div>
   </body>`,
  { runScripts: "outside-only", pretendToBeVisual: true }
);
const { window } = dom;
const { document } = window;

/* jsdom 에는 캔버스 2D 컨텍스트가 없다. 우리가 확인하려는 것은 그리기 결과가
   아니라 DOM 이동이므로, 컨텍스트는 호출만 기록하는 가짜로 대신한다. */
window.HTMLCanvasElement.prototype.getContext = function () {
  return {
    fillStyle: "",
    drawImage() {},
    fillRect() {},
    putImageData() {},
    getImageData: () => ({ data: [] }),
  };
};
window.HTMLCanvasElement.prototype.toDataURL = () => "data:image/png;base64,AA";

/* getBoundingClientRect 가 0 을 돌려주면 좌표 환산이 0 으로 나눠진다.
   실제 브라우저처럼 크기를 가진 사각형을 돌려준다. */
window.Element.prototype.getBoundingClientRect = function () {
  return { left: 0, top: 0, width: 500, height: 700, right: 500, bottom: 700 };
};

const img = document.querySelector("img");
Object.defineProperty(img, "naturalWidth", { value: 500 });
Object.defineProperty(img, "naturalHeight", { value: 700 });
Object.defineProperty(img, "complete", { value: true });

window.eval(SRC + "\n;window.Redact = Redact;");
const Redact = window.Redact;

const figure = document.querySelector("figure");
const preview = document.getElementById("preview");

let fails = 0;
function ok(label, cond) {
  console.log((cond ? "  통과  " : "  실패  ") + label);
  if (!cond) fails += 1;
}

function ev(type, x, y, target) {
  const e = new window.MouseEvent(type, {
    clientX: x, clientY: y, bubbles: true, cancelable: true,
  });
  (target || canvas).dispatchEvent(e);
}

/* 1. 그림이 캔버스로 바뀐다 */
let counted = -1;
Redact.enableAll(preview, (n) => { counted = n; });
const canvas = figure.querySelector("canvas");
ok("img 가 canvas 로 바뀐다", !!canvas);
ok("figure 안에 img 가 남아 있지 않다", !figure.querySelector("img"));

/* 2. 끌면 칠해진다 */
ev("mousedown", 40, 40);
ev("mousemove", 200, 120);
ev("mouseup", 200, 120, window);
ok("끌면 칸이 하나 생긴다", figure._redact.count() === 1);
ok("콜백으로 칸 수가 전달된다", counted === 1);

/* 3. 끈 직후의 클릭은 확대를 열지 않는다 (칠하다가 창이 뜨면 방해된다) */
ev("click", 200, 120);
ok("끈 직후 클릭은 확대를 열지 않는다",
   !document.querySelector(".redact-modal.on"));

/* 4. 그냥 누르면 확대가 열리고, 캔버스가 '옮겨진다' */
ev("mousedown", 60, 60);
ev("mouseup", 60, 60, window);
ev("click", 60, 60);

const overlay = document.querySelector(".redact-modal");
const stage = overlay && overlay.querySelector(".redact-modal-stage");
ok("확대 창이 열린다", !!overlay && overlay.classList.contains("on"));
ok("캔버스가 확대 창 안으로 들어간다", stage && stage.firstElementChild === canvas);
ok("같은 캔버스다 (복사본이 아니다)", stage && stage.querySelector("canvas") === canvas);
ok("확대용 클래스가 붙는다", canvas.classList.contains("redact-canvas-large"));
ok("원래 자리에 표시자가 남는다", !!figure.querySelector(".redact-slot"));
ok("칠한 칸은 그대로 1칸", figure._redact.count() === 1);
ok("배경 스크롤이 잠긴다", document.body.style.overflow === "hidden");

/* 5. 확대 창에서도 되돌리기가 동작한다 */
ev("mousedown", 30, 300);
ev("mousemove", 260, 380);
ev("mouseup", 260, 380, window);
ok("확대 창에서도 칠할 수 있다", figure._redact.count() === 2);

overlay.querySelector('[data-act="undo"]').dispatchEvent(
  new window.MouseEvent("click", { bubbles: true })
);
ok("확대 창의 되돌리기가 한 칸을 지운다", figure._redact.count() === 1);

/* 6. 닫으면 같은 캔버스가 제자리로 돌아온다 */
overlay.querySelector('[data-act="close"]').dispatchEvent(
  new window.MouseEvent("click", { bubbles: true })
);
ok("확대 창이 닫힌다", !overlay.classList.contains("on"));
ok("같은 캔버스가 figure 로 돌아온다", figure.querySelector("canvas") === canvas);
ok("확대용 클래스가 떨어진다", !canvas.classList.contains("redact-canvas-large"));
ok("표시자가 사라진다", !figure.querySelector(".redact-slot"));
ok("칠한 칸이 유실되지 않는다", figure._redact.count() === 1);
ok("배경 스크롤이 풀린다", document.body.style.overflow === "");
ok("확대 창 안에 캔버스가 남아 있지 않다", !overlay.querySelector("canvas"));

/* 7. Esc 로도 닫힌다 */
ev("mousedown", 60, 60);
ev("mouseup", 60, 60, window);
ev("click", 60, 60);
ok("다시 열린다", overlay.classList.contains("on"));
document.dispatchEvent(
  new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true })
);
ok("Esc 로 닫힌다", !overlay.classList.contains("on"));
ok("Esc 로 닫아도 캔버스가 제자리", figure.querySelector("canvas") === canvas);

/* 8. 전체 되돌리기·초기화가 여전히 동작한다 */
Redact.resetAll(preview);
ok("초기화하면 칸이 없어진다", figure._redact.count() === 0);

console.log(fails === 0 ? "\n확대 모달 테스트 전부 통과" : `\n실패 ${fails}건`);
process.exit(fails === 0 ? 0 : 1);
