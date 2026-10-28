/**
 * 펴봄 사전 설문 자동 생성 (Google Apps Script)
 *
 * 사용법
 *   1. https://script.google.com → 새 프로젝트
 *   2. 이 코드를 전부 붙여넣고 저장
 *   3. 위쪽 함수 선택에서 createPyeobomSurvey 를 고르고 [실행]
 *   4. 처음 실행하면 구글 권한 승인 화면이 나온다(내 계정에 폼·시트를 만드는 권한)
 *   5. 아래 [실행 로그]에 응답 링크·편집 링크·응답 시트 링크가 찍힌다
 *
 * 결과: 내 구글 드라이브에 폼 1개 + 응답 저장용 스프레드시트 1개
 * 설계: 세탁기·에어컨은 "주로 쓰는 한 대"만 묻는다(응답 1건 = 시트 1행, 가공이 쉽도록)
 * 문항 원본: docs/설문-문항.md
 */

function createPyeobomSurvey() {
  const form = FormApp.create('펴봄 사전 설문 — 자취생 가전 사용 실태');
  form.setDescription([
    '펴봄(가전 설명서 Q&A 서비스) 1차 프로젝트를 위한 3분 설문입니다.',
    '이름·연락처·이메일은 받지 않으며, 결과는 집계해서 프로젝트 문서와 발표에만 씁니다.',
    '세탁기·에어컨은 지금 주로 쓰는 한 대를 기준으로 답해 주세요.',
    '모델명은 제품에 붙은 라벨에서 확인할 수 있어요(위치는 제품마다 달라요). 모르면 비워 두세요.'
  ].join('\n'));
  form.setProgressBar(true);
  form.setAllowResponseEdits(false);
  form.setConfirmationMessage('응답해 주셔서 감사합니다! 결과는 집계해서 펴봄 프로젝트에만 사용합니다.');
  try {
    form.setCollectEmail(false); // 이메일 수집 안 함
  } catch (e) {
    Logger.log('이메일 수집 설정을 코드로 바꾸지 못했습니다. 폼 [설정] 탭에서 직접 꺼 주세요: ' + e);
  }

  // ---------- 섹션 1. 기본 ----------
  addRadio_(form, 'Q01 [기본] 지금 사는 곳', [
    '원룸·오피스텔(옵션 가전 있음)',
    '원룸·오피스텔(옵션 가전 없음)',
    '셰어하우스·기숙사',
    '본가·가족과 거주'
  ], { other: true });
  const hasWasher = form.addMultipleChoiceItem()
    .setTitle('Q02 [세탁기] 지금 쓰는 세탁기가 있나요?')
    .setRequired(true); // 선택지는 아래에서 섹션 이동과 함께 지정

  // ---------- 섹션 2. 세탁기 ----------
  form.addPageBreakItem()
    .setTitle('세탁기')
    .setHelpText('주로 쓰는 세탁기 한 대를 기준으로 답해 주세요.');
  addRadio_(form, 'Q03 [세탁기] 브랜드', ['삼성', 'LG', '모름'], { other: true });
  addRadio_(form, 'Q04 [세탁기] 종류', [
    '통돌이',
    '드럼',
    '세탁건조기 일체형',
    '세탁조 2개 결합형',
    '모름'
  ], { help: '통돌이 = 위에서 여는 형태 / 드럼 = 앞에서 여는 형태 / 세탁건조기 일체형 = 한 대로 세탁과 건조' });
  addText_(form, 'Q05 [세탁기] 모델명', '라벨에 적힌 영문·숫자 조합. 모르면 비워 두세요.');
  addRadio_(form, 'Q06 [세탁기] 설명서 보유', [
    '종이 설명서 있음',
    'PDF·앱으로 본 적 있음',
    '없음',
    '모름'
  ]);

  // ---------- 섹션 3. 에어컨 여부 ----------
  const airconAskPage = form.addPageBreakItem().setTitle('에어컨');
  const hasAircon = form.addMultipleChoiceItem()
    .setTitle('Q07 [에어컨] 지금 쓰는 에어컨이 있나요?')
    .setRequired(true);

  // ---------- 섹션 4. 에어컨 ----------
  form.addPageBreakItem()
    .setTitle('에어컨 정보')
    .setHelpText('주로 쓰는 에어컨 한 대를 기준으로 답해 주세요.');
  addRadio_(form, 'Q08 [에어컨] 브랜드', ['삼성', 'LG', '캐리어', '위니아', '파세코', '위닉스', '모름'], { other: true });
  addRadio_(form, 'Q09 [에어컨] 종류', ['벽걸이', '스탠드', '창문형', '천장형(시스템)', '이동식', '모름']);
  addText_(form, 'Q10 [에어컨] 모델명', '라벨에 적힌 영문·숫자 조합. 모르면 비워 두세요.');
  addRadio_(form, 'Q11 [에어컨] 설명서 보유', [
    '종이 설명서 있음',
    'PDF·앱으로 본 적 있음',
    '없음',
    '모름'
  ]);

  // ---------- 섹션 5. 막혔던 경험 여부 ----------
  const issueAskPage = form.addPageBreakItem().setTitle('막혔던 경험');
  const hadIssue = form.addMultipleChoiceItem()
    .setTitle('Q12 [경험] 최근 6개월 안에 세탁기나 에어컨을 쓰다가 막힌 적이 있나요?')
    .setRequired(true);

  // ---------- 섹션 6. 경험 상세 ----------
  form.addPageBreakItem().setTitle('그때 이야기');
  addCheckbox_(form, 'Q13 [경험] 어떤 상황이었나요? (여러 개 선택)', [
    '에러 코드가 떴다',
    '기능·사용법을 몰랐다(예약·통세척·모드 등)',
    '청소·관리 방법을 몰랐다(필터 등)',
    '고장인지 아닌지 몰랐다'
  ]);
  addCheckbox_(form, 'Q14 [경험] 어떻게 해결하려고 했나요? (여러 개 선택)', [
    '인터넷 검색(포털·블로그·영상)',
    '제조사 사이트·앱',
    '종이 설명서',
    '고객센터·AS 전화',
    '집주인·관리인 문의',
    'AI 챗봇(ChatGPT 등)',
    '포기했다'
  ]);
  addRadio_(form, 'Q15 [경험] 해결까지 걸린 시간', ['5분 이내', '5~15분', '15~30분', '30분 이상', '해결 못 함']);
  addRadio_(form, 'Q16 [경험] 찾은 정보가 다른 모델 이야기여서 헷갈린 적이 있나요?', ['있다', '없다', '잘 모르겠다']);
  addText_(form, 'Q17 [경험] 가장 불편했던 점 한 줄', '선택 사항');

  // ---------- 섹션 7. 서비스 의향 ----------
  const intentPage = form.addPageBreakItem().setTitle('서비스 의향');
  form.addScaleItem()
    .setTitle('Q18 [의향] 모델을 고르고 질문하면 공식 설명서·제조사 가이드의 근거(쪽·출처)와 함께 답해 주는 서비스를 써 볼 생각이 있나요?')
    .setBounds(1, 5)
    .setLabels('전혀 없음', '꼭 써 보고 싶음')
    .setRequired(true);
  addRadio_(form, 'Q19 [의향] 이런 서비스에서 가장 중요한 것', [
    '정확한 답',
    '빠른 답',
    '근거(쪽·출처) 표시',
    '쉬운 말'
  ], { other: true });
  form.addParagraphTextItem()
    .setTitle('Q20 [기타] 다른 세탁기·에어컨이 더 있거나 하고 싶은 말')
    .setHelpText('선택 사항. 두 번째 가전이 있다면 브랜드·종류·모델명을 적어 주세요.')
    .setRequired(false);
  addRadio_(form, 'Q21 [테스트] 10/30~11/2 중 10분짜리 사용자 테스트에 참여할 수 있나요?', ['예', '아니요'], {
    help: '"예"라면 캠프 채널에서 따로 알려 주세요. 설문에서는 연락처를 받지 않아요.'
  });

  // ---------- 섹션 이동 설정 (모든 섹션을 만든 뒤 지정) ----------
  hasWasher.setChoices([
    hasWasher.createChoice('있음', FormApp.PageNavigationType.CONTINUE), // → 섹션 2(세탁기)
    hasWasher.createChoice('없음', airconAskPage)                         // → 섹션 3(에어컨 여부)
  ]);
  hasAircon.setChoices([
    hasAircon.createChoice('있음', FormApp.PageNavigationType.CONTINUE), // → 섹션 4(에어컨 정보)
    hasAircon.createChoice('없음', issueAskPage)                          // → 섹션 5(경험 여부)
  ]);
  hadIssue.setChoices([
    hadIssue.createChoice('예', FormApp.PageNavigationType.CONTINUE),    // → 섹션 6(경험 상세)
    hadIssue.createChoice('아니요', intentPage)                           // → 섹션 7(서비스 의향)
  ]);
  // 섹션 2·4·6은 끝나면 순서대로 다음 섹션으로 가므로 따로 설정하지 않는다.

  // ---------- 응답 저장용 스프레드시트 연결 ----------
  const sheet = SpreadsheetApp.create('펴봄 사전 설문 응답');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());

  Logger.log('응답 링크(배포용): ' + form.getPublishedUrl());
  Logger.log('편집 링크: ' + form.getEditUrl());
  Logger.log('응답 시트: ' + sheet.getUrl());
}

/** 객관식(하나만 선택). options: { other: 기타 입력칸, help: 설명, required: 기본 true } */
function addRadio_(form, title, choices, options) {
  const opts = options || {};
  const item = form.addMultipleChoiceItem()
    .setTitle(title)
    .setChoiceValues(choices)
    .setRequired(opts.required !== false);
  if (opts.other) item.showOtherOption(true);
  if (opts.help) item.setHelpText(opts.help);
  return item;
}

/** 체크박스(여러 개 선택). 응답 시트에는 ", "로 이어져 한 칸에 저장되므로 선택지에 쉼표를 쓰지 않는다. */
function addCheckbox_(form, title, choices) {
  return form.addCheckboxItem()
    .setTitle(title)
    .setChoiceValues(choices)
    .showOtherOption(true)
    .setRequired(true);
}

/** 단답형(선택 입력) */
function addText_(form, title, help) {
  return form.addTextItem()
    .setTitle(title)
    .setHelpText(help)
    .setRequired(false);
}
