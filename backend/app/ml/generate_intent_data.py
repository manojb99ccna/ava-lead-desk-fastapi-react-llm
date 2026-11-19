"""Generates a large synthetic training set for Ava's intent classifier.

Templates x slot values x "real-world noise" (typos, chat abbreviations, Hinglish fillers,
missing punctuation, WhatsApp-style short text).

    python -m app.ml.generate_intent_data --per-intent 3500 --to-db
        -> writes app/ml/data/intent_dataset.csv AND replaces the source='generated' rows in
           ava_sys_intent_training_examples (rows with source='manual' are never touched).

Synthetic data teaches vocabulary and robustness; the hand-written set in
app/ml/data/intent_eval.csv is the honest measure of real-world accuracy.
"""
import argparse
import csv
import os
import random

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_FILE = os.path.join(DATA_DIR, "intent_dataset.csv")

SLOTS = {
    "service": ["website", "web site", "website design", "web app", "web application", "online store", "ecommerce site",
                "e-commerce website", "shopify store", "landing page", "portfolio site", "mobile friendly website",
                "website redesign", "maintenance", "website maintenance", "seo", "crm", "booking system", "dashboard",
                "admin panel", "wordpress site", "logo and website", "business website", "app"],
    "day": ["today", "tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
            "next week", "this week", "the weekend", "next monday", "day after tomorrow"],
    "time": ["10am", "11 am", "2pm", "3 pm", "4:30", "morning", "afternoon", "evening", "noon", "after lunch",
             "9 o'clock", "5pm"],
    "name": ["Rahul", "Priya", "Amit", "Sneha", "John", "Sara", "Vikram", "Anjali", "Mohammed", "Neha", "David",
             "Pooja", "Arjun", "Kavya", "Ravi"],
    "thing": ["quote", "estimate", "proposal", "quotation", "price list", "invoice", "callback", "call back"],
}

TEMPLATES = {
    "greeting": [
        "nice to meet you", "glad to find a chat here", "hello, quick question about {service}", "hey, am i talking to ava", "hi, can i ask something", "hello there team",
        "hi", "hello", "hey", "hey there", "hii", "hello ava", "hi ava", "good morning", "good afternoon",
        "good evening", "namaste", "hola", "yo", "hi there", "hello anyone there", "is anyone there", "hey ava",
        "hi i need some help", "hello i have a question", "hi team", "greetings", "hello sir", "hi mam",
        "hey how are you", "hi, how r u", "hello good morning", "hey i'm {name}", "hi this is {name}",
    ],
    "goodbye": [
        "talk soon", "cheers", "later", "ok i will leave it here", "gotta run", "signing off", "bye for now",
        "bye", "goodbye", "bye bye", "see you", "see ya", "talk later", "that's all", "that is all thank you",
        "ok bye", "thanks bye", "have a nice day", "catch you later", "i'm done", "nothing else", "no that's it",
        "good night", "ok cool bye", "will get back later bye", "thats all for now", "ttyl",
    ],
    "thanks": [
        "really helpful", "that was useful", "thanks, very helpful", "great help", "brilliant, thanks", "you have been helpful",
        "thanks", "thank you", "thank you so much", "thanks a lot", "thx", "ty", "many thanks", "great thanks",
        "awesome thank you", "thanks for the help", "appreciate it", "that helped thanks", "perfect thanks",
        "thank you ava", "cool thanks", "nice, thank you", "super thanks", "thanks for the info",
    ],
    "appointment": [
        "can we do a video call {day}", "zoom call {day}?", "google meet {day} {time}", "can i visit your office {day}", "quick call {day} to discuss {service}", "i want to come in {day}",
        "i want to book an appointment", "book an appointment", "can i book a meeting", "schedule a meeting",
        "i'd like to schedule a consultation", "book a consultation for {service}", "can we meet {day}",
        "are you free {day} at {time}", "i need an appointment", "set up a call {day}", "book a slot",
        "can i get an appointment {day} {time}", "i want to meet your team", "schedule a demo",
        "book a free consultation", "fix a meeting for {day}", "i want to discuss my {service} project in a meeting",
        "available for a call {day}?", "book me in for {time} {day}", "when can i come for a meeting",
        "i'd like to make a booking", "make an appointment for me", "can i schedule a call about {service}",
        "is {day} {time} free for a meeting", "need a consultation", "let's set a meeting",
    ],
    "cancel_appointment": [
        "call off my {day} consultation", "call off the appointment", "scrap my booking", "i will not come {day}, cancel", "please withdraw my appointment",
        "cancel my appointment", "i want to cancel my booking", "please cancel the meeting", "cancel my meeting on {day}",
        "i can't make it {day}, cancel it", "cancel the consultation", "i need to cancel", "drop my appointment",
        "please cancel my slot", "call off the meeting", "i won't be able to come, cancel please",
        "cancel booking AVA-7K3P9Q", "remove my appointment", "delete my booking", "i want to cancel the {time} meeting",
        "cancel my {day} appointment please", "no longer need the appointment", "cancel it please",
    ],
    "reschedule_appointment": [
        "reschedule my appointment", "can i change my appointment time", "move my meeting to {day}",
        "change my booking to {time}", "i want to reschedule", "can we shift the meeting to {day} {time}",
        "postpone my appointment", "change the date of my appointment", "i need a different time",
        "can i move my slot", "push my meeting to next week", "prepone my appointment to {day}",
        "change my consultation to {day}", "shift my booking", "i can't come at {time}, can we change it",
        "need to change my appointment", "rebook my meeting for {day}",
    ],
    "business_hours": [
        "what are your opening hours", "when are you open", "are you open {day}", "what time do you open",
        "what time do you close", "office timings", "working hours", "are you open on weekends",
        "do you work on sunday", "till what time are you open", "are you open now", "what are your hours",
        "opening time", "closing time", "timings please", "are you open on saturday", "is the office open {day}",
        "what days are you open", "business hours?", "when does your office open {day}",
    ],
    "contact": [
        "how can i contact you", "what is your phone number", "give me your email", "where is your office",
        "what's your address", "how do i reach you", "contact details please", "can i call you",
        "share your number", "what is your email id", "office location", "where are you located",
        "do you have a whatsapp number", "your contact number?", "how to get in touch", "send me your address",
        "what's the best way to contact your team",
    ],
    "pricing": [
        "is a {service} under 20k", "can i get a {service} for 10000", "what is the minimum budget", "approx cost of {service}", "ballpark figure for {service}", "is {service} affordable",
        "how much does a {service} cost", "what are your prices", "price for {service}", "how much do you charge",
        "what is the cost of a {service}", "rates for {service}", "is it expensive", "pricing please",
        "what's your fee", "{service} price", "budget for a {service}", "how much for a {service}",
        "cost?", "what are the charges", "do you have packages", "starting price for {service}",
        "what would a {service} cost me", "is there a monthly fee for {service}", "price range",
        "how much is it", "cheap {service} price",
    ],
    "services": [
        "do you handle {service} projects", "is {service} something you do", "do you work with small businesses",
        "what services do you offer", "what do you do", "do you build {service}", "can you make a {service}",
        "do you do {service}", "list your services", "what can you help me with", "do you offer {service}",
        "can you develop a {service}", "what kind of work do you do", "services?", "do you make mobile apps",
        "can you redesign my website", "do you provide hosting", "can you help with {service}",
        "what products do you have", "are you a web development company", "tell me about your services",
        "can you build a {service} for my shop",
    ],
    "lead_inquiry": [
        "i need a {thing} for a {service}", "can you send me a {thing}", "please call me back",
        "i'm interested in a {service}", "i want a {service} for my business", "can someone call me",
        "give me a {thing} for {service}", "i have a project, can we discuss", "i want to start a {service} project",
        "contact me about a {service}", "need a {service}, please get in touch", "my number is 98765xxxxx call me",
        "request a {thing}", "i'd like a callback {day}", "interested, please share details", "send me a proposal",
        "i want to hire you for a {service}", "looking for someone to build a {service}",
        "we need a {service} for our company", "can i get a free estimate", "pls call me {day} {time}",
    ],
    "follow_up": [
        "i filled your form and got no reply", "no one got back to me", "i emailed you {day} but no response", "haven't received any reply yet", "what happened to my enquiry", "i'm waiting since {day}",
        "any update on my {thing}", "i haven't heard back", "you said you would call me", "what's the status of my request",
        "did you get my enquiry", "following up on my {thing}", "nobody called me yet", "still waiting for the {thing}",
        "any news about my project", "i submitted a request {day}, any update", "when will i get the {thing}",
        "checking on my previous message", "is my request being processed", "update please",
        "i was promised a callback", "following up regarding the {service}", "status of my booking?",
    ],
    "human_escalation": [
        "i want to talk to a human", "connect me to a real person", "can i speak to someone", "talk to an agent",
        "i need a representative", "let me talk to your staff", "transfer me to a person", "i want to speak to the manager",
        "is there a human i can talk to", "get me a real person", "speak to customer support", "human please",
        "i don't want to talk to a bot", "can a person call me", "connect to support team", "i need human help",
        "put me through to someone", "agent please",
    ],
    "complaint": [
        "my {service} keeps crashing", "the {service} you built is down", "site not loading since {day}", "payment page is not working", "we have a problem with the work you delivered", "error on my website",
        "i'm not happy with the service", "this is terrible", "my website is broken", "i want to complain",
        "your team never responded", "very bad experience", "the site you made is not working", "i'm really disappointed",
        "worst service ever", "nobody is helping me", "my {service} has a bug", "i'm frustrated",
        "you missed the deadline", "the work quality is poor", "i want to raise a complaint", "this is unacceptable",
    ],
    "refund_policy": [
        "what is your refund policy", "can i get my money back", "do you give refunds", "how do refunds work",
        "i want a refund", "is there a money back guarantee", "refund terms", "cancellation and refund policy",
        "will i get a refund if i cancel", "refund please", "what if i'm not satisfied", "return policy",
        "can i get refund for {service}", "how long does a refund take",
    ],
    "affirm": [
        "yes", "yes please", "yeah", "yep", "sure", "ok", "okay", "ok sure", "sounds good", "go ahead", "please do",
        "yes book it", "yes that's right", "correct", "that's correct", "absolutely", "of course", "why not",
        "alright", "fine", "ya", "haan", "haan ji", "theek hai", "yes i would like that", "sure, let's do it",
    ],
    "decline": [
        "no", "nope", "no thanks", "no thank you", "not now", "not really", "nah", "maybe later", "not interested",
        "i don't want any booking", "i dont want an appointment", "no need", "i'm just looking", "just browsing",
        "not today", "no i'm good", "i'm fine thanks", "leave it", "forget it", "never mind", "nahi", "nahi chahiye",
        "rehne do", "no i don't need that", "i don't want to book",
    ],
    "out_of_scope": [
        "help me with my maths homework", "solve this equation", "write my essay", "what is the score", "who is the best actor", "how do i lose weight", "tell me today's news",
        "what's the weather", "tell me a joke", "who won the match", "what is the capital of france",
        "can you do my homework", "sing a song", "what is 2+2", "who is the prime minister", "recommend a movie",
        "how to cook pasta", "what's bitcoin price", "are you married", "write me a poem", "translate this to french",
        "what is the meaning of life", "play music", "order pizza", "book a flight", "what time is it in london",
        "how tall is mount everest",
    ],
}

PREFIXES = ["", "", "", "", "hi ", "hello ", "hey ", "sir ", "bhai ", "please ", "pls ", "ok ", "um ", "so ",
            "excuse me ", "quick question ", "ava ", "hii ", "dear team "]
SUFFIXES = ["", "", "", "", "?", "??", "!", ".", " please", " pls", " plz", " sir", " ji", " asap", " thanks",
            " thx", " :)", " 🙏", " na", " bro"]
WORD_SWAPS = {
    "you": ["u", "you", "yu"], "your": ["ur", "your", "yr"], "are": ["r", "are"], "please": ["pls", "plz", "please"],
    "what": ["wat", "what", "wht"], "tomorrow": ["tmrw", "tomorow", "tomorrow"], "appointment": ["appt", "appointmnt",
    "appointment", "apointment"], "thanks": ["thx", "thnx", "thanks"], "want": ["wanna", "want", "wnt"],
    "because": ["coz", "bcz"], "i": ["i", "I"], "is": ["is", "s"], "the": ["the", "da", ""], "meeting": ["meeting",
    "meting", "mtg"], "schedule": ["schedule", "shedule", "schdule"], "cancel": ["cancel", "cancle", "cancell"],
    "price": ["price", "prize", "pric"], "website": ["website", "websit", "web site", "site"],
    "business": ["business", "bussiness", "busines"], "available": ["available", "availble", "avail"],
}
HINGLISH = {
    "appointment": ["appointment chahiye", "mujhe appointment book karna hai", "appointment milega kya {day}",
                    "kal meeting fix karo", "meeting book kar do"],
    "pricing": ["kitna lagega {service} ka", "price kya hai", "{service} ka rate kya hai", "kitne ka padega"],
    "business_hours": ["office kab khulta hai", "aaj open hai kya", "timing kya hai", "sunday ko open ho kya"],
    "services": ["aap kya kya karte ho", "{service} banate ho kya", "kya aap {service} bana sakte ho"],
    "human_escalation": ["kisi insaan se baat karni hai", "manager se baat karao", "real person se baat karwao"],
    "cancel_appointment": ["meeting cancel kar do", "appointment cancel karna hai", "mera booking cancel karo"],
    "reschedule_appointment": ["meeting {day} pe shift kar do", "time change karna hai", "appointment aage kar do"],
    "lead_inquiry": ["mujhe {service} chahiye", "quotation bhejo", "call back karo please", "mujhe call karo {day}"],
    "follow_up": ["koi update", "abhi tak call nahi aaya", "mera kaam kahan tak pahuncha"],
    "greeting": ["namaste ji", "kaise ho", "hello ji"],
    "goodbye": ["chalo bye", "theek hai bye", "baad mein baat karte hain"],
    "thanks": ["dhanyavaad", "shukriya", "thank you ji"],
    "complaint": ["bahut bekaar service", "website kaam nahi kar rahi", "koi jawab nahi de raha"],
    "refund_policy": ["paise wapas milenge kya", "refund milega kya"],
    "contact": ["number do", "office kahan hai", "email id kya hai"],
}


def fill(template: str, rng: random.Random) -> str:
    out = template
    for slot, values in SLOTS.items():
        while "{" + slot + "}" in out:
            out = out.replace("{" + slot + "}", rng.choice(values), 1)
    return out


def typo(word: str, rng: random.Random) -> str:
    if len(word) < 4 or not word.isalpha():
        return word
    i = rng.randrange(1, len(word) - 1)
    op = rng.random()
    if op < 0.33:
        return word[:i] + word[i + 1:]  # drop a letter
    if op < 0.66:
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]  # swap neighbours
    return word[:i] + word[i] + word[i:]  # double a letter


def noisy(text: str, rng: random.Random) -> str:
    words = []
    for w in text.split():
        key = w.lower().strip("?,.!")
        if key in WORD_SWAPS and rng.random() < 0.35:
            w = rng.choice(WORD_SWAPS[key])
        elif rng.random() < 0.07:
            w = typo(w, rng)
        if w:
            words.append(w)
    text = " ".join(words)
    text = rng.choice(PREFIXES) + text + rng.choice(SUFFIXES)
    r = rng.random()
    if r < 0.15:
        text = text.upper()
    elif r < 0.45:
        text = text.capitalize()
    if rng.random() < 0.3:
        text = text.replace(",", "").replace("'", "")
    return " ".join(text.split())


def generate(per_intent: int, seed: int) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    rows = []
    for intent, templates in TEMPLATES.items():
        pool = templates + HINGLISH.get(intent, []) * 2
        seen = set()
        attempts = 0
        while len(seen) < per_intent and attempts < per_intent * 30:
            attempts += 1
            text = fill(rng.choice(pool), rng)
            if rng.random() < 0.85:
                text = noisy(text, rng)
            text = text.strip()
            if text and text.lower() not in seen:
                seen.add(text.lower())
                rows.append((text, intent))
    rng.shuffle(rows)
    return rows


def import_to_db(rows: list[tuple[str, str]], batch_size: int = 5000) -> int:
    """Replaces all generated examples in ava_sys_intent_training_examples. Manual rows are kept."""
    from sqlalchemy import delete, insert

    from app.database import SessionLocal
    from app.models import AvaSysIntent, AvaSysIntentTrainingExample

    db = SessionLocal()
    try:
        intent_ids = {i.name: i.id for i in db.query(AvaSysIntent).all()}
        for name in sorted({intent for _, intent in rows} - set(intent_ids)):
            intent = AvaSysIntent(name=name, description=f"{name.replace('_', ' ')} (generated)", is_active=True)
            db.add(intent)
            db.flush()
            intent_ids[name] = intent.id
        db.execute(delete(AvaSysIntentTrainingExample).where(AvaSysIntentTrainingExample.source == "generated"))
        payload = [{"intent_id": intent_ids[intent], "text": text[:1000], "source": "generated", "is_active": True}
                   for text, intent in rows]
        for start in range(0, len(payload), batch_size):
            db.execute(insert(AvaSysIntentTrainingExample), payload[start:start + batch_size])
        db.commit()
        return len(payload)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-intent", type=int, default=3500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=OUT_FILE)
    parser.add_argument("--to-db", action="store_true", help="also store the examples in the database")
    args = parser.parse_args()
    rows = generate(args.per_intent, args.seed)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "intent"])
        writer.writerows(rows)
    counts = {}
    for _, intent in rows:
        counts[intent] = counts.get(intent, 0) + 1
    print(f"Wrote {len(rows)} examples to {args.out}")
    for intent, n in sorted(counts.items()):
        print(f"  {intent:24s} {n}")
    if args.to_db:
        print(f"Stored {import_to_db(rows)} generated examples in ava_sys_intent_training_examples")


if __name__ == "__main__":
    main()
