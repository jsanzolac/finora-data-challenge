/**
 * Exact rational arithmetic on BigInt, for the funnel maths.
 *
 * The contract asks for exact decimals (never floats) so the screen matches the
 * gold views. Money and rates arrive as decimal strings; products of rates and
 * divisions by Won are kept as exact fractions and rounded HALF_UP (half away
 * from zero, like Spark and Java's BigDecimal) only when they are displayed.
 */

function abs(value: bigint): bigint {
  return value < 0n ? -value : value;
}

function gcd(a: bigint, b: bigint): bigint {
  let x = abs(a);
  let y = abs(b);
  while (y !== 0n) {
    [x, y] = [y, x % y];
  }
  return x;
}

const DECIMAL = /^([+-]?)(\d+)(?:\.(\d+))?$/;

export class Ratio {
  readonly num: bigint;
  /** Always positive. */
  readonly den: bigint;

  private constructor(num: bigint, den: bigint) {
    if (den === 0n) throw new RangeError("Division by zero");
    const sign = den < 0n ? -1n : 1n;
    const divisor = gcd(num, den) || 1n;
    this.num = (sign * num) / divisor;
    this.den = (sign * den) / divisor;
  }

  static of(num: bigint | number, den: bigint | number = 1n): Ratio {
    return new Ratio(BigInt(num), BigInt(den));
  }

  static readonly ZERO = Ratio.of(0n);
  static readonly ONE = Ratio.of(1n);

  /** Parses a plain decimal string ("200000000", "-0.016", "0.8000"). Throws on anything else. */
  static parse(text: string): Ratio {
    const match = DECIMAL.exec(text.trim());
    if (!match) throw new SyntaxError(`Not a decimal: ${JSON.stringify(text)}`);
    const [, sign = "", whole = "0", fraction = ""] = match;
    const num = BigInt(whole + fraction) * (sign === "-" ? -1n : 1n);
    return new Ratio(num, 10n ** BigInt(fraction.length));
  }

  /** `parse`, or null for anything that is not a plain decimal string. */
  static tryParse(text: string | null | undefined): Ratio | null {
    if (typeof text !== "string") return null;
    try {
      return Ratio.parse(text);
    } catch {
      return null;
    }
  }

  add(other: Ratio): Ratio {
    return new Ratio(this.num * other.den + other.num * this.den, this.den * other.den);
  }

  sub(other: Ratio): Ratio {
    return new Ratio(this.num * other.den - other.num * this.den, this.den * other.den);
  }

  mul(other: Ratio): Ratio {
    return new Ratio(this.num * other.num, this.den * other.den);
  }

  div(other: Ratio): Ratio {
    if (other.num === 0n) throw new RangeError("Division by zero");
    return new Ratio(this.num * other.den, this.den * other.num);
  }

  neg(): Ratio {
    return new Ratio(-this.num, this.den);
  }

  isZero(): boolean {
    return this.num === 0n;
  }

  sign(): -1 | 0 | 1 {
    return this.num === 0n ? 0 : this.num > 0n ? 1 : -1;
  }

  compare(other: Ratio): -1 | 0 | 1 {
    return this.sub(other).sign();
  }

  equals(other: Ratio): boolean {
    return this.num === other.num && this.den === other.den;
  }

  /** True when the value has at most `places` decimals. */
  hasAtMostDecimals(places: number): boolean {
    return (this.num * 10n ** BigInt(places)) % this.den === 0n;
  }

  /** The value rounded HALF_UP (half away from zero) to `places` decimals, as a scaled integer. */
  roundScaled(places: number): bigint {
    const scale = 10n ** BigInt(places);
    const scaled = abs(this.num) * scale;
    const rounded = (2n * scaled + this.den) / (2n * this.den);
    return this.num < 0n ? -rounded : rounded;
  }

  /** "1234.50" style: HALF_UP to `places` decimals, no grouping. */
  toFixed(places: number): string {
    const rounded = this.roundScaled(places);
    const negative = rounded < 0n;
    const digits = abs(rounded).toString().padStart(places + 1, "0");
    const whole = places > 0 ? digits.slice(0, -places) : digits;
    const fraction = places > 0 ? `.${digits.slice(-places)}` : "";
    return `${negative ? "-" : ""}${whole}${fraction}`;
  }

  /** For drawing only (chart geometry). Never used in the funnel arithmetic. */
  toNumber(): number {
    return Number(this.toFixed(12));
  }
}
