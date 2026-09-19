/* 판정 결과를 화면에 그린다.
 *
 * 합치기 전 프론트에는 이 층이 없었다. 서버를 호출해 결과를 받아
 * window.contractAnalysisResult 에 넣어 두기는 하는데, 그걸 읽는 코드가 없었다.
 * 결과 화면은 제7조 위약금·제9조 연차처럼 손으로 써 둔 예시가 그대로 떠 있었다.
 *
 * 그래서 어떤 계약서를 올려도 같은 화면이 나왔다. 심사위원이 자기 계약서를 넣으면
 * 바로 드러난다. 디자인은 그대로 두고, 그 자리에 진짜 결과를 채워 넣는 층을 만든다.
 *
 * 서버가 주는 것과 화면이 쓰는 말이 다르므로 여기서 옮긴다.
 *   violation   -> 확인 필요 (status-warning)
 *   unfavorable -> 확인 필요 (같은 칸에 표시하되 문구로 구분)
 *   dropped     -> 인용 검증에서 걸러진 판정. 서랍에 따로 보여준다.
 */

const Render = (() => {
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function $(id) {
    return document.getElementById(id);
  }

  /* 판정 하나 -> 카드 한 장. 프론트의 기존 마크업 구조를 그대로 따른다.
     클래스 이름을 바꾸면 style.css 가 안 먹으므로 건드리지 않는다. */
  function card(f, i) {
    const warning = f.severity === "violation";
    const statusText = warning ? "확인 필요" : "확인 권장";
    const statusClass = warning ? "status-warning" : "status-caution";
    // 카드 제목은 짧아야 한다. '제N조(제목)' 형식이면 그대로 쓰고,
    // 표·번호 목록형 계약서처럼 조 번호가 없으면 항목명만 뽑는다.
    // 안 그러면 제목 자리에 조항 본문이 통째로 들어가 카드가 무너진다.
    const title = f.clause_title || "계약서 전체";
    const num = (title.match(/제\s*\d+\s*조/) || [""])[0];
    let name = title.replace(/제\s*\d+\s*조\s*/, "").trim();
    if (name.includes(":")) name = name.split(":")[0].trim();     // '임 금 : 월 160만원' -> '임 금'
    name = name.replace(/^\d+[.)]\s*/, "").trim();                 // '6. 임금' -> '임금'
    if (name.length > 24) name = name.slice(0, 24) + "…";
    if (!name) name = "해당 조항";

    const search = [title, f.reason, f.law_label, f.clause_text]
      .filter(Boolean).join(" ").slice(0, 400);

    const quote = f.clause_text
      ? `<div class="contract-quote">&ldquo;${esc(f.clause_text.slice(0, 300))}${
          f.clause_text.length > 300 ? "…" : ""}&rdquo;</div>`
      : "";

    const suggestion = f.suggestion
      ? `<div class="analysis-section"><h3>어떻게 고치면 되나요?</h3><p>${esc(f.suggestion)}</p></div>`
      : "";

    // 근거 조문은 서버가 인용 검증을 통과시킨 것만 보낸다.
    // '원문 확인' 배지는 그 검증을 통과했다는 뜻이지 장식이 아니다.
    const law = f.law_label
      ? `<div class="analysis-section">
           <h3>관련 법적 근거</h3>
           <div class="law-reference">
             <div class="law-reference-heading">
               <div>
                 <strong>${esc(f.law_label.split("(")[0].trim())}</strong>
                 <span>${esc((f.law_label.match(/\(([^)]*)\)/) || [, ""])[1])}</span>
               </div>
               <span class="verified-badge">원문 확인</span>
             </div>
             <blockquote>${esc(f.quote || f.law_text || "")}</blockquote>
           </div>
         </div>`
      : "";

    return `
      <article id="finding-${i}" class="analysis-card${i === 0 ? " selected" : ""}"
               data-status="warning" data-search="${esc(search)}">
        <div class="analysis-card-header">
          <div>
            ${num ? `<span class="clause-number">${esc(num)}</span>` : ""}
            <h2>${esc(name)}</h2>
          </div>
          <span class="status ${statusClass}">${statusText}</span>
        </div>
        ${quote}
        <div class="analysis-section">
          <h3>왜 확인이 필요한가요?</h3>
          <p>${esc(f.reason || "")}</p>
        </div>
        ${law}
        ${suggestion}
      </article>`;
  }

  /* 판정 결과 전체를 화면에 반영한다. */
  function apply(result) {
    if (!result) return;
    const meta = result.meta || {};
    const findings = result.findings || [];
    const total = meta.clause_count || (result.clauses || []).length;
    const flagged = findings.length;
    const clean = Math.max(total - flagged, 0);
    const dropped = (result.dropped || []).length;

    // ── 위험도. 산식을 그대로 보여준다.
    //    근거 없는 숫자는 신뢰를 얻지 못한다. 서버가 계산한 식을 그대로 받아 띄운다.
    const risk = meta.risk;
    const box = $("riskBox");
    if (box && risk) {
      box.style.display = "";
      const num = $("riskNumber");
      if (num) num.textContent = risk.score;
      const grade = $("riskGrade");
      if (grade) grade.textContent = risk.grade || "";
      const rmsg = $("riskMessage");
      if (rmsg) rmsg.textContent = risk.message || "";
      const formula = $("riskFormula");
      if (formula) formula.textContent = risk.formula || "";
      // 점수대에 따라 색만 바꾼다. 클래스는 style.css 가 정의한 것을 쓴다.
      box.dataset.level = risk.score >= 61 ? "high" : risk.score >= 26 ? "mid" : "low";
    }

    // ── 요약 문장
    const msg = document.querySelector(".summary-message h2");
    if (msg) {
      msg.innerHTML = flagged
        ? `${total}개 조항 중 <strong>${flagged}개 조항</strong>을 확인해 주세요.`
        : `${total}개 조항을 살펴봤고 <strong>확인이 필요한 조항을 찾지 못했습니다.</strong>`;
    }
    const sub = document.querySelector(".summary-message p");
    if (sub && !flagged) {
      sub.textContent = "법령과 대조해 문제되는 조항을 찾지 못했습니다. "
        + "다만 계약서에 적히지 않은 실제 근무조건까지는 확인할 수 없습니다.";
    }

    // ── 숫자 네 칸
    const nums = document.querySelectorAll(".summary-numbers strong");
    if (nums.length >= 4) {
      nums[0].textContent = total;
      nums[1].textContent = flagged;
      nums[2].textContent = clean;
      nums[3].textContent = dropped;
    }

    // ── 인용 검증 배너. 이 서비스의 핵심이라 숫자를 정확히 말한다.
    const banner = $("verificationBanner");
    if (banner) {
      const span = banner.querySelector("span:nth-child(2)");
      if (span) {
        span.innerHTML = dropped
          ? `<strong>법령 원문 검증이 작동했습니다.</strong> 근거를 확인할 수 없었던 판단 ${dropped}건을 결과에서 제외했습니다.`
          : `<strong>법령 원문 검증을 통과했습니다.</strong> 표시된 근거 조문은 모두 법령 원문과 글자 단위로 일치합니다.`;
      }
    }

    // ── 카드 목록
    const list = document.querySelector(".analysis-list");
    if (list) {
      list.innerHTML = findings.length
        ? findings.map(card).join("")
        : "";
    }
    const empty = $("emptyResult");
    if (empty) empty.classList.toggle("hidden", findings.length > 0);

    // ── 필터 버튼의 개수
    const fw = document.querySelector('[data-filter="warning"]');
    if (fw) fw.textContent = `확인 필요 ${flagged}`;
    const fs = document.querySelector('[data-filter="safe"]');
    if (fs) fs.textContent = `특이사항 없음 ${clean}`;

    // ── 마스킹 안내. 가렸다는 사실은 사용자가 알아야 한다.
    if (meta.masked_message) {
      let note = $("maskedNotice");
      if (!note) {
        note = document.createElement("div");
        note.id = "maskedNotice";
        note.className = "verification-banner";
        note.style.cursor = "default";
        const anchor = $("verificationBanner");
        if (anchor && anchor.parentNode) {
          anchor.parentNode.insertBefore(note, anchor.nextSibling);
        }
      }
      note.innerHTML = `<span class="banner-shield">＊</span><span>`
        + `<strong>${esc(meta.masked_message)}</strong> `
        + `이름·주민등록번호 같은 정보는 판정에 쓰이지 않아 검사 전에 가렸습니다.</span>`;
    }
  }

  /* 분석할 수 없는 입력(판독 실패, 근로계약서 아님)을 알린다.
     이때 점수를 보여주면 안 된다. '문제 없음'으로 읽히기 때문이다. */
  function blocked(result) {
    const meta = result.meta || {};
    const check = meta.input_check || {};
    const doc = meta.doctype;

    if (check.ok === false) {
      return { title: check.title, message: check.message };
    }
    if (meta.analyzable === false && doc) {
      const contractor = doc.kind === "contractor";
      return {
        title: contractor ? "근로계약서가 아닌 계약서로 보입니다"
                          : "근로계약서로 보이지 않습니다",
        message: (contractor
          ? "이 서비스는 근로기준법 등 근로자에게 적용되는 법과 대조합니다. "
            + "용역·위탁·프리랜서 계약은 근로기준법이 적용되지 않으므로 같은 기준으로 "
            + "검토하면 틀린 법을 들이대는 것이 됩니다. 그래서 점수를 내지 않습니다. "
          : "이 서비스는 근로계약서만 검토합니다. 다른 문서에는 대조할 법조문이 없습니다. ")
          + (doc.reasons || []).join(" "),
        disguise: doc.disguise_warning,
      };
    }
    return null;
  }

  return { apply, blocked };
})();
