import test from "node:test";
import assert from "node:assert/strict";
import { wheelToScroll } from "../../../public/js/wheel.js";

const box = (scrollLeft, scrollWidth = 432, clientWidth = 360) => ({ scrollLeft, scrollWidth, clientWidth });
const down = (deltaY, more = {}) => ({ deltaX: 0, deltaY, deltaMode: 0, ctrlKey: false, shiftKey: false, ...more });

test("가로로 넘칠 때 세로 휠은 가로 이동 양(px)", () => {
  assert.equal(wheelToScroll(down(100), box(0)), 100);
  assert.equal(wheelToScroll(down(-100), box(50)), -100);
});

test("안 넘치면 0(화면이 스크롤)", () => {
  assert.equal(wheelToScroll(down(100), box(0, 360, 360)), 0);
});

test("그 방향 끝이면 0(휠이 갇히지 않게)", () => {
  assert.equal(wheelToScroll(down(100), box(72)), 0);       // 오른쪽 끝(432 - 360)
  assert.equal(wheelToScroll(down(100), box(71.5)), 0);     // 소수 스크롤 위치도 끝으로 본다
  assert.equal(wheelToScroll(down(-100), box(0)), 0);       // 왼쪽 끝
  assert.equal(wheelToScroll(down(-100), box(72)), -100);   // 오른쪽 끝에서 위로 굴리면 왼쪽으로
});

test("가로 휠·Shift+휠·Ctrl+휠은 0(브라우저 기본 동작)", () => {
  assert.equal(wheelToScroll(down(0, { deltaX: 40 }), box(0)), 0);
  assert.equal(wheelToScroll(down(10, { deltaX: 40 }), box(0)), 0);   // 옆으로 더 민 트랙패드
  assert.equal(wheelToScroll(down(100, { shiftKey: true }), box(0)), 0);
  assert.equal(wheelToScroll(down(100, { ctrlKey: true }), box(0)), 0);
});

test("줄·쪽 단위는 픽셀로 환산", () => {
  assert.equal(wheelToScroll(down(3, { deltaMode: 1 }), box(0)), 48);    // 줄 = 16px
  assert.equal(wheelToScroll(down(1, { deltaMode: 2 }), box(0)), 360);   // 쪽 = 보이는 폭
});
