import {
  BarChartIcon,
  CandlestickIcon,
  DatabaseIcon,
  FunnelIcon,
  LineChartIcon,
  MatrixIcon,
  NetworkIcon,
  PieChartIcon,
  ScatterIcon,
  TrendUpIcon,
} from "./Icons";

// Purely decorative motifs (charts, network graphs, econometric notation)
// that drift slowly behind the app content - themes the background around
// Economics / Data Science / Econometrics without competing with the UI.
const ITEMS = [
  { Icon: LineChartIcon, top: "9%", left: "6%", size: 52, duration: 24, delay: 0, drift: "a" },
  { symbol: "Σ", top: "16%", left: "89%", size: 56, duration: 27, delay: 2, drift: "b" },
  { Icon: ScatterIcon, top: "64%", left: "4%", size: 54, duration: 25, delay: 1, drift: "c" },
  { symbol: "β₁", top: "80%", left: "85%", size: 38, duration: 21, delay: 3, drift: "a" },
  { Icon: BarChartIcon, top: "38%", left: "93%", size: 46, duration: 29, delay: 4, drift: "b" },
  { Icon: NetworkIcon, top: "86%", left: "46%", size: 46, duration: 26, delay: 1.5, drift: "c" },
  { symbol: "R²", top: "5%", left: "45%", size: 32, duration: 22, delay: 2.5, drift: "a" },
  { Icon: PieChartIcon, top: "50%", left: "15%", size: 40, duration: 30, delay: 0.5, drift: "b" },
  { symbol: "ŷ = β₀+β₁x", top: "29%", left: "20%", size: 18, duration: 23, delay: 3.5, drift: "c" },
  { Icon: TrendUpIcon, top: "12%", left: "68%", size: 44, duration: 26, delay: 2, drift: "b" },
  { Icon: CandlestickIcon, top: "70%", left: "62%", size: 44, duration: 24, delay: 0.8, drift: "a" },
  { Icon: MatrixIcon, top: "34%", left: "3%", size: 42, duration: 28, delay: 3.2, drift: "c" },
  { Icon: DatabaseIcon, top: "6%", left: "24%", size: 38, duration: 25, delay: 1.2, drift: "b" },
  { Icon: FunnelIcon, top: "92%", left: "16%", size: 34, duration: 22, delay: 2.8, drift: "a" },
  { symbol: "π", top: "44%", left: "78%", size: 40, duration: 20, delay: 0.3, drift: "c" },
  { symbol: "μ", top: "58%", left: "94%", size: 34, duration: 24, delay: 1.8, drift: "a" },
  { symbol: "λ", top: "22%", left: "3%", size: 30, duration: 23, delay: 4.2, drift: "b" },
  { symbol: "p < 0.05", top: "94%", left: "68%", size: 16, duration: 27, delay: 2.2, drift: "c" },
  { symbol: "H₀", top: "60%", left: "34%", size: 26, duration: 21, delay: 3.8, drift: "a" },
  { symbol: "∆", top: "76%", left: "9%", size: 30, duration: 25, delay: 1.6, drift: "b" },
];

export default function FloatingBackground() {
  return (
    <div className="floating-bg" aria-hidden="true">
      {ITEMS.map((item, i) => (
        <span
          key={i}
          className={`floating-item floating-drift-${item.drift} ${item.symbol ? "floating-symbol" : ""}`}
          style={{
            top: item.top,
            left: item.left,
            fontSize: item.size,
            animationDuration: `${item.duration}s`,
            animationDelay: `${item.delay}s`,
          }}
        >
          {item.Icon ? <item.Icon /> : item.symbol}
        </span>
      ))}
    </div>
  );
}
