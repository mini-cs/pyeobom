// 옆으로 넘기는 줄(카테고리 타일·추천 카드)에서 마우스 세로 휠을 가로 이동으로 바꿀 양(px).
// 0이면 바꾸지 않는다: 가로 휠·Shift+휠·Ctrl+휠(확대)은 브라우저 기본 동작, 안 넘치거나 그 방향 끝이면 화면이 스크롤(휠이 갇히지 않게).
const LINE_PX = 16;  // deltaMode 1(줄 단위, 주로 Firefox)의 한 줄

export function wheelToScroll({ deltaX, deltaY, deltaMode, ctrlKey, shiftKey }, { scrollLeft, scrollWidth, clientWidth }) {
  if (ctrlKey || shiftKey || !deltaY || Math.abs(deltaX) >= Math.abs(deltaY)) return 0;
  const max = scrollWidth - clientWidth;
  const px = deltaY * (deltaMode === 1 ? LINE_PX : deltaMode === 2 ? clientWidth : 1);
  const atEnd = px > 0 ? scrollLeft >= max - 1 : scrollLeft <= 0;  // 소수 스크롤 위치는 1px 안이면 끝
  return max <= 0 || atEnd ? 0 : px;
}
