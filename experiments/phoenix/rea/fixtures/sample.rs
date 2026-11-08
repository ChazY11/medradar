// PHOENIX-001 REA validation fixture (harmless, native PE).
// Compiled with rustc to produce an unsigned, freshly built x86-64 PE that
// REA's built-in PE inspection can be tested against.

const MARKER: &str = "phoenix-001-rea-validation-marker";

fn digest(payload: &str) -> u64 {
    let mut hash: u64 = 0xcbf29ce484222325;
    for b in payload.as_bytes() {
        hash ^= *b as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    hash
}

fn classify(value: i32) -> &'static str {
    if value < 0 {
        "negative"
    } else if value == 0 {
        "zero"
    } else {
        "positive"
    }
}

fn main() {
    println!("{}", MARKER);
    println!("{:016x}", digest("phoenix-001"));
    println!("{},{},{}", classify(-1), classify(0), classify(1));
}
