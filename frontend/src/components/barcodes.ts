// Frame barcodes (requirements §6.1); same rules as the backend's app/frames/barcodes.py.
// New codes: five letters and a Luhn mod 26 check letter, shown as ABC-DEF. Old codes
// ABCD-EFGH (no check letter) are printed on existing frames and stay valid.

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const N = ALPHABET.length;

const NEW_PATTERN = /^[A-Z]{3}-[A-Z]{3}$/;
const OLD_PATTERN = /^[A-Z]{4}-[A-Z]{4}$/;

/** Luhn mod 26 check letter for the given letters. */
export function checkLetter(payload: string): string {
  let total = 0;
  let factor = 2;
  for (const char of [...payload].reverse()) {
    const addend = factor * ALPHABET.indexOf(char);
    total += Math.floor(addend / N) + (addend % N);
    factor = factor === 2 ? 1 : 2;
  }
  return ALPHABET[(N - (total % N)) % N]!;
}

/** Why the (upper-case) code is not a valid barcode, or null if it is. */
export function barcodeProblem(code: string): string | null {
  if (OLD_PATTERN.test(code)) return null;
  if (!NEW_PATTERN.test(code)) return `"${code}" is not a barcode (format ABC-DEF)`;
  const letters = code.replace("-", "");
  if (checkLetter(letters.slice(0, 5)) !== letters[5]) {
    return `"${code}": check letter does not match, mistyped?`;
  }
  return null;
}
