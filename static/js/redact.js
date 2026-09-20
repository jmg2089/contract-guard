/* 미리보기 그림 위에 직접 검은 칠을 할 수 있게 한다.
 *
 * 왜 필요한가.
 *
 * 자동 인식은 100%가 될 수 없다. 사진이 기울었거나, 글씨가 흐리거나, 우리가 모르는
 * 라벨 표기를 쓰면 놓친다. 그때 "자동 인식은 완전하지 않습니다"라고 적어 두는 것으로는
 * 사용자가 할 수 있는 일이 없다. 놓친 걸 봤는데 고칠 방법이 없으면 더 불안하다.
 *
 * 그래서 끌어서 칠할 수 있게 한다. 기계가 놓친 자리를 사람이 덮는다.
 *
 * 다만 분명히 해 둘 것이 있다. 이 그림에 칠하는 것은 **그림에만** 적용된다.
 * 실제 판정은 아래 입력창의 글자로 하므로, 놓친 개인정보가 있으면 입력창에서도
 * 지워야 한다. 화면에 그렇게 적어 둔다. 가렸다고 착각하게 만드는 것이 가장 나쁘다.
 */

const Redact = (() => {
  /* 미리보기 <img> 를 캔버스로 바꿔 그 위에 칠할 수 있게 만든다. */
  function enable(figure, onChange) {
    const img = figure.querySelector("img");
    if (!img || figure.dataset.redactReady === "1") return;

    const draw = () => {
      try {
        build();
      } catch (e) {
        // 그림을 캔버스로 못 옮기면 칠하기만 못 할 뿐, 나머지는 그대로 둔다.
        // 여기서 예외가 밖으로 나가면 미리보기 전체가 깨진다.
      }
    };

    const build = () => {
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      canvas.className = "redact-canvas";
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0);

      // 사용자가 칠한 사각형만 따로 기억한다. 되돌리기를 하려면 원본이 있어야 한다.
      const base = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const boxes = [];

      const repaint = () => {
        ctx.putImageData(base, 0, 0);
        ctx.fillStyle = "#111";
        boxes.forEach((b) => ctx.fillRect(b.x, b.y, b.w, b.h));
      };

      // 화면 좌표 -> 이미지 좌표. 이미지는 CSS 로 축소돼 있으므로 배율을 맞춰야 한다.
      const toImage = (ev) => {
        const r = canvas.getBoundingClientRect();
        const p = ev.touches ? ev.touches[0] : ev;
        return {
          x: (p.clientX - r.left) * (canvas.width / r.width),
          y: (p.clientY - r.top) * (canvas.height / r.height),
        };
      };

      let start = null;

      const begin = (ev) => {
        ev.preventDefault();
        start = toImage(ev);
      };

      const move = (ev) => {
        if (!start) return;
        ev.preventDefault();
        const now = toImage(ev);
        repaint();
        ctx.fillStyle = "rgba(17,17,17,0.55)";
        ctx.fillRect(
          Math.min(start.x, now.x), Math.min(start.y, now.y),
          Math.abs(now.x - start.x), Math.abs(now.y - start.y)
        );
      };

      const end = (ev) => {
        if (!start) return;
        const now = toImage(ev);
        const w = Math.abs(now.x - start.x);
        const h = Math.abs(now.y - start.y);
        // 손이 미끄러진 정도는 칠하지 않는다
        if (w > 4 && h > 4) {
          boxes.push({
            x: Math.min(start.x, now.x), y: Math.min(start.y, now.y), w, h,
          });
        }
        start = null;
        repaint();
        if (onChange) onChange(boxes.length);
      };

      canvas.addEventListener("mousedown", begin);
      canvas.addEventListener("mousemove", move);
      window.addEventListener("mouseup", end);
      canvas.addEventListener("touchstart", begin, { passive: false });
      canvas.addEventListener("touchmove", move, { passive: false });
      canvas.addEventListener("touchend", end);

      img.replaceWith(canvas);
      figure.dataset.redactReady = "1";

      figure._redact = {
        canvas,
        undo() {
          boxes.pop();
          repaint();
          if (onChange) onChange(boxes.length);
        },
        reset() {
          boxes.length = 0;
          repaint();
          if (onChange) onChange(0);
        },
        count() { return boxes.length; },
      };
    };

    if (img.complete && img.naturalWidth) draw();
    else img.addEventListener("load", draw, { once: true });
  }

  /* 미리보기 영역 전체를 칠할 수 있게 만든다. */
  function enableAll(container, onChange) {
    if (!container) return;
    container.querySelectorAll("figure").forEach((f) => enable(f, onChange));
  }

  function undoAll(container) {
    if (!container) return;
    container.querySelectorAll("figure").forEach((f) => f._redact && f._redact.undo());
  }

  function resetAll(container) {
    if (!container) return;
    container.querySelectorAll("figure").forEach((f) => f._redact && f._redact.reset());
  }

  /* 칠한 그림을 내려받는다. 사용자가 다른 곳에 보낼 때 쓸 수 있는 결과물이다. */
  function download(container) {
    if (!container) return;
    const canvases = container.querySelectorAll("canvas");
    if (!canvases.length) {
      window.alert("내려받을 그림이 없습니다.");
      return;
    }
    canvases.forEach((c, i) => {
      const a = document.createElement("a");
      a.href = c.toDataURL("image/png");
      a.download = canvases.length > 1
        ? `가린-계약서-${i + 1}쪽.png`
        : "가린-계약서.png";
      a.click();
    });
  }

  return { enableAll, undoAll, resetAll, download };
})();
