/* jsdom ships no 2D canvas. Provide a stub that records the draw calls so the
   flame renderer can be exercised in tests without the native `canvas`
   package. It deliberately does NOT fake plausible pixels: coverage-style
   assertions against a stub would only test the stub. Anything about shape or
   intensity is asserted through the pure parameters instead. */
class StubGradient {
  addColorStop() {}
}

const installed: string[] = [];

if (typeof HTMLCanvasElement !== "undefined") {
  HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, kind: string) {
    if (kind !== "2d") return null;
    installed.push("2d");
    const ctx = {
      canvas: this,
      fillStyle: "",
      strokeStyle: "",
      globalAlpha: 1,
      calls: 0,
      createRadialGradient: () => new StubGradient(),
      createLinearGradient: () => new StubGradient(),
      beginPath() {
        this.calls++;
      },
      closePath() {},
      moveTo() {},
      lineTo() {},
      bezierCurveTo() {},
      quadraticCurveTo() {},
      arc() {},
      ellipse() {},
      rect() {},
      fill() {},
      stroke() {},
      clearRect() {},
      save() {},
      restore() {},
      translate() {},
      scale() {},
      rotate() {},
      getImageData: (_x: number, _y: number, w: number, h: number) => ({
        width: w,
        height: h,
        data: new Uint8ClampedArray(w * h * 4),
        colorSpace: "srgb" as const,
      }),
      putImageData() {},
    };
    return ctx as unknown as CanvasRenderingContext2D;
  } as unknown as HTMLCanvasElement["getContext"];
}

export const canvasStubHits = () => installed.length;