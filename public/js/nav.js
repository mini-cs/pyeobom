// 서랍 ← 버튼의 한 단계 위 주소. 채팅 → 그 가전의 모델 고르기, 모델 고르기 → 가전 고르기, 그 위는 없음(⌂와 같아서 숨김)
export function parentHash(route, models) {
  if (route.screen === "model") return "#category";
  if (route.screen !== "chat") return null;
  const model = models.find((m) => m.id === route.modelId);
  return model ? `#model/${encodeURIComponent(model.appliance)}` : "#category";  // 목록을 못 받았거나 모르는 모델
}
