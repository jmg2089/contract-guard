/* 전송 전에 브라우저에서 민감정보를 가린다.
 *
 * 서버도 같은 처리를 하지만(core/mask.py), 서버에서만 가리면 이미 늦다.
 * 주민등록번호가 네트워크를 타고 서버 메모리에 한 번은 올라가기 때문이다.
 * 여기서 먼저 가리면 그 정보는 사용자 기기 밖으로 나가지 않는다.
 *
 * 정규식은 core/mask.py 와 같아야 한다. 한쪽만 고치면 안내 문구와 실제 동작이 어긋난다.
 * 순서도 같다 — 계좌번호 패턴이 카드번호·휴대전화를 먹으므로 좁은 것을 먼저 돌린다.
 */

const Mask = (() => {
  const PATTERNS = [
    ["주민등록번호", /(?<![0-9])(\d{6})\s*[-–]\s*([1-8])\d{6}(?![0-9])/g, "$1-$2******"],
    ["카드번호", /(?<![0-9])(\d{4})[- ](\d{4})[- ](\d{4})[- ](\d{4})(?![0-9])/g, "$1-****-****-****"],
    ["전화번호", /(?<![0-9])(01[016-9])[-. ]?(\d{3,4})[-. ]?(\d{4})(?![0-9])/g, "$1-****-****"],
    ["계좌번호", /(?<![0-9-])(\d{2,6})-(\d{2,6})-(\d{2,7})(?![0-9-])/g, "$1-****-****"],
    ["이메일", /(?<![\w.])([\w.+-]{1,3})[\w.+-]*@([\w-]+\.[\w.]+)/g, "$1***@$2"],
  ];

  /* 텍스트 -> { text, counts }.
     counts 는 화면에 "민감정보 3건을 가렸습니다"를 띄우기 위한 것이다.
     조용히 처리하면 사용자는 무슨 일이 있었는지 모른다. 보호는 보여야 신뢰가 된다. */
  function apply(text) {
    const counts = {};
    let out = text || "";
    for (const [name, re, repl] of PATTERNS) {
      let n = 0;
      out = out.replace(re, (...args) => {
        n += 1;
        // replace 콜백에서 $1 치환을 직접 처리한다
        return repl.replace(/\$(\d)/g, (_, d) => args[Number(d)]);
      });
      if (n) counts[name] = n;
    }
    return { text: out, counts };
  }

  function summary(counts) {
    const keys = Object.keys(counts);
    if (!keys.length) return "";
    const total = keys.reduce((s, k) => s + counts[k], 0);
    const parts = keys.map((k) => `${k} ${counts[k]}건`);
    return `민감정보 ${total}건을 가린 뒤 보냈습니다 (${parts.join(", ")}). 이 정보는 검사에 쓰이지 않습니다.`;
  }

  /* 미리 훑어보기 — 아직 가리지 않고 몇 건이 있는지만 센다.
     사용자가 [검사하기]를 누르기 전에 알려주기 위한 것이다. */
  function scan(text) {
    return apply(text).counts;
  }

  return { apply, summary, scan };
})();
