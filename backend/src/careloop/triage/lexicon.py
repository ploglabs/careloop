"""Red-flag phrases per language, scanned on every final STT transcript.

`latn` holds English and romanised (Hinglish-style) phrases. It is checked on every call,
because patients mix English medical words into every language and code-mixed STT output
may be transliterated.

Indic-script phrases are matched as substrings, since symptoms take case suffixes
(e.g. ಜ್ವರ → ಜ್ವರವಿದೆ). Latin phrases are matched on word boundaries.

These lists need native-speaker and clinician review before production use.
"""

from dataclasses import dataclass

from careloop.models import Urgency


@dataclass(frozen=True)
class RedFlag:
    id: str
    level: Urgency
    reason: str
    terms: dict[str, tuple[str, ...]]


def _rf(id: str, level: Urgency, reason: str, **terms: list[str]) -> RedFlag:
    return RedFlag(id, level, reason, {k.replace("_", "-") + ("" if k == "latn" else "-IN"): tuple(v) for k, v in terms.items()})


E, U, R = Urgency.EMERGENCY, Urgency.URGENT, Urgency.REVIEW

RED_FLAGS: tuple[RedFlag, ...] = (
    # ---- EMERGENCY ----
    _rf(
        "lex_chest_pain", E, "Chest pain",
        latn=["chest pain", "chest tightness", "pain in my chest", "pain in chest", "seene mein dard",
              "seene me dard", "chhati mein dard", "chhati me dard", "chest me pain", "chest mein pain"],
        hi=["सीने में दर्द", "छाती में दर्द", "सीने में जकड़न"],
        bn=["বুকে ব্যথা", "বুকে ব্যাথা"],
        gu=["છાતીમાં દુખાવો", "છાતીમાં દુઃખાવો"],
        kn=["ಎದೆ ನೋವು", "ಎದೆನೋವು"],
        ml=["നെഞ്ചുവേദന", "നെഞ്ച് വേദന"],
        mr=["छातीत दुखत", "छातीत दुखणे", "छातीत वेदना"],
        pa=["ਛਾਤੀ ਵਿੱਚ ਦਰਦ", "ਛਾਤੀ 'ਚ ਦਰਦ", "ਛਾਤੀ ਵਿਚ ਦਰਦ"],
        ta=["நெஞ்சு வலி", "நெஞ்சுவலி", "மார்பு வலி"],
        te=["ఛాతీ నొప్పి", "ఛాతి నొప్పి", "గుండె నొప్పి"],
    ),
    _rf(
        "lex_breathing", E, "Difficulty breathing",
        latn=["can't breathe", "cannot breathe", "cant breathe", "not able to breathe", "unable to breathe",
              "difficulty breathing", "trouble breathing", "short of breath", "shortness of breath",
              "breathless", "saans nahi", "saans nahin", "saans lene mein takleef", "saans lene me takleef",
              "saans lene mein dikkat", "saans lene me dikkat", "saans lene mein taklif", "sans lene mein dikkat",
              "saans phool", "dum ghut"],
        hi=["सांस नहीं", "साँस नहीं", "सांस लेने में तकलीफ", "साँस लेने में तकलीफ", "सांस लेने में दिक्कत",
            "साँस लेने में दिक्कत", "सांस फूल", "साँस फूल", "दम घुट"],
        bn=["শ্বাস নিতে কষ্ট", "শ্বাসকষ্ট", "দম বন্ধ"],
        gu=["શ્વાસ લેવામાં તકલીફ", "શ્વાસ નથી", "શ્વાસ ચઢ"],
        kn=["ಉಸಿರಾಟದ ತೊಂದರೆ", "ಉಸಿರು ಕಟ್ಟ", "ಉಸಿರಾಡಲು ಕಷ್ಟ"],
        ml=["ശ്വാസം മുട്ട", "ശ്വാസതടസ്സം", "ശ്വസിക്കാൻ ബുദ്ധിമുട്ട"],
        mr=["श्वास घेण्यास त्रास", "श्वास घ्यायला त्रास", "दम लाग"],
        pa=["ਸਾਹ ਲੈਣ ਵਿੱਚ ਤਕਲੀਫ਼", "ਸਾਹ ਲੈਣ ਵਿੱਚ ਤਕਲੀਫ", "ਸਾਹ ਨਹੀਂ", "ਸਾਹ ਚੜ੍ਹ"],
        ta=["மூச்சு விட முடியல", "மூச்சு விட முடியவில்லை", "மூச்சுத் திணறல்", "மூச்சு திணறல்", "மூச்சு விட கஷ்டம்"],
        te=["ఊపిరి ఆడటం లేదు", "ఊపిరి ఆడట్లేదు", "శ్వాస తీసుకోవడం కష్టం", "ఆయాసం"],
    ),
    _rf(
        "lex_heavy_bleeding", E, "Heavy or uncontrolled bleeding",
        latn=["heavy bleeding", "bleeding a lot", "bleeding heavily", "won't stop bleeding", "bleeding won't stop",
              "bleeding wont stop", "lot of blood", "bahut khoon", "khoon band nahi", "khoon ruk nahi"],
        hi=["बहुत खून", "खून बंद नहीं", "खून रुक नहीं", "ज़्यादा खून", "ज्यादा खून"],
        bn=["অনেক রক্ত", "রক্ত বন্ধ হচ্ছে না"],
        gu=["ખૂબ લોહી", "લોહી બંધ નથી"],
        kn=["ತುಂಬಾ ರಕ್ತ", "ರಕ್ತ ನಿಲ್ಲುತ್ತಿಲ್ಲ"],
        ml=["ധാരാളം രക്തം", "രക്തം നിൽക്കുന്നില്ല"],
        mr=["खूप रक्त", "रक्त थांबत नाही"],
        pa=["ਬਹੁਤ ਖੂਨ", "ਖੂਨ ਬੰਦ ਨਹੀਂ"],
        ta=["நிறைய ரத்தம்", "ரத்தம் நிற்கவில்லை", "இரத்தம் நிற்கவில்லை"],
        te=["చాలా రక్తం", "రక్తం ఆగడం లేదు"],
    ),
    _rf(
        "lex_vomit_blood", E, "Vomiting blood or black stool",
        latn=["vomiting blood", "blood in vomit", "black stool", "khoon ki ulti", "khoon ki ultee"],
        hi=["खून की उल्टी", "काला मल"],
        bn=["রক্ত বমি"],
        gu=["લોહીની ઉલટી"],
        kn=["ರಕ್ತ ವಾಂತಿ"],
        ml=["രക്തം ഛർദ്ദി"],
        mr=["रक्ताची उलटी"],
        pa=["ਖੂਨ ਦੀ ਉਲਟੀ"],
        ta=["ரத்த வாந்தி"],
        te=["రక్తపు వాంతి", "రక్తం వాంతి"],
    ),
    _rf(
        "lex_fainting", E, "Fainting or loss of consciousness",
        latn=["fainted", "passed out", "unconscious", "blacked out", "behosh", "behoshi"],
        hi=["बेहोश"],
        bn=["অজ্ঞান", "জ্ঞান হারিয়ে"],
        gu=["બેભાન"],
        kn=["ಪ್ರಜ್ಞೆ ತಪ್ಪಿ", "ಮೂರ್ಛೆ ಹೋಗ"],
        ml=["ബോധം കെട്ട", "ബോധക്ഷയം"],
        mr=["बेशुद्ध"],
        pa=["ਬੇਹੋਸ਼"],
        ta=["மயக்கம் போட்டு", "மயங்கி விழு", "மயங்கி விழுந்"],
        te=["స్పృహ తప్పి", "కళ్ళు తిరిగి పడి"],
    ),
    _rf(
        "lex_anaphylaxis", E, "Swelling of face, lips or throat (possible severe allergic reaction)",
        latn=["face swelling", "swelling of face", "face is swollen", "lips swelling", "lips are swollen",
              "swollen lips", "throat swelling", "throat is closing", "tongue swelling", "honth sooj", "gala sooj"],
        hi=["होंठ सूज", "चेहरा सूज", "गले में सूजन", "जीभ सूज"],
        bn=["ঠোঁট ফুলে", "মুখ ফুলে", "গলা ফুলে"],
        gu=["હોઠ સૂજી", "ચહેરો સૂજી", "ગળામાં સોજો"],
        kn=["ತುಟಿ ಊದ", "ಮುಖ ಊದ", "ಗಂಟಲು ಊದ"],
        ml=["ചുണ്ട് വീങ്ങ", "മുഖം വീങ്ങ", "തൊണ്ട വീങ്ങ"],
        mr=["ओठ सुज", "चेहरा सुज", "घसा सुज"],
        pa=["ਬੁੱਲ੍ਹ ਸੁੱਜ", "ਚਿਹਰਾ ਸੁੱਜ", "ਗਲਾ ਸੁੱਜ"],
        ta=["உதடு வீங்க", "முகம் வீங்க", "தொண்டை வீங்க"],
        te=["పెదవులు వాచ", "ముఖం వాచ", "గొంతు వాచ"],
    ),
    _rf(
        "lex_seizure", E, "Seizure",
        latn=["seizure", "fits", "convulsion", "mirgi", "daura pada", "daura padaa"],
        hi=["मिर्गी", "दौरा पड़", "दौरे पड़"],
        bn=["খিঁচুনি"],
        gu=["આંચકી", "ખેંચ આવી"],
        kn=["ಫಿಟ್ಸ್", "ಸೆಳವು"],
        ml=["അപസ്മാരം"],
        mr=["फिट आली", "आकडी"],
        pa=["ਦੌਰਾ ਪਿਆ", "ਮਿਰਗੀ"],
        ta=["வலிப்பு"],
        te=["ఫిట్స్", "మూర్ఛ"],
    ),
    _rf(
        "lex_stroke", E, "Possible stroke signs",
        latn=["face drooping", "slurred speech", "can't move my arm", "one side weak", "paralysis", "lakwa"],
        hi=["लकवा", "बोलने में दिक्कत", "मुँह टेढ़ा"],
    ),
    _rf(
        "lex_self_harm", E, "Self-harm or suicidal thoughts",
        latn=["suicide", "kill myself", "end my life", "want to die", "khudkushi"],
        hi=["आत्महत्या", "जान दे दूं", "मरना चाहता", "मरना चाहती"],
        bn=["আত্মহত্যা"],
        gu=["આત્મહત્યા"],
        kn=["ಆತ್ಮಹತ್ಯೆ"],
        ml=["ആത്മഹത്യ"],
        mr=["आत्महत्या"],
        pa=["ਖੁਦਕੁਸ਼ੀ", "ਆਤਮਹੱਤਿਆ"],
        ta=["தற்கொலை"],
        te=["ఆత్మహత్య"],
    ),
    # ---- URGENT ----
    _rf(
        "lex_high_fever", U, "High fever",
        latn=["high fever", "very high fever", "fever is very high", "tez bukhar", "tez bukhaar", "bahut bukhar"],
        hi=["तेज़ बुखार", "तेज बुखार", "बहुत बुखार"],
        bn=["খুব জ্বর", "প্রচণ্ড জ্বর"],
        gu=["ખૂબ તાવ", "સખત તાવ"],
        kn=["ತೀವ್ರ ಜ್ವರ", "ಜಾಸ್ತಿ ಜ್ವರ"],
        ml=["കടുത്ത പനി", "നല്ല പനി"],
        mr=["खूप ताप", "जास्त ताप"],
        pa=["ਤੇਜ਼ ਬੁਖਾਰ", "ਬਹੁਤ ਬੁਖਾਰ"],
        ta=["அதிக காய்ச்சல்", "கடுமையான காய்ச்சல்"],
        te=["ఎక్కువ జ్వరం", "తీవ్రమైన జ్వరం"],
    ),
    _rf(
        "lex_pus", U, "Pus or foul-smelling discharge",
        latn=["pus", "oozing", "foul smell", "smells bad", "mawad", "peep aa"],
        hi=["मवाद", "पस निकल"],
        bn=["পুঁজ"],
        gu=["પરુ"],
        kn=["ಕೀವು"],
        ml=["പഴുപ്പ്"],
        mr=["पू येत", "पू आला", "पू निघ"],
        pa=["ਪੀਕ", "ਪਸ"],
        ta=["சீழ்"],
        te=["చీము"],
    ),
    _rf(
        "lex_severe_pain", U, "Severe pain",
        latn=["severe pain", "unbearable pain", "worst pain", "pain is unbearable", "bahut tez dard", "bahut zyada dard",
              "bahut jyada dard", "sahan nahi"],
        hi=["बहुत तेज़ दर्द", "बहुत तेज दर्द", "असहनीय दर्द", "बहुत ज़्यादा दर्द", "बहुत ज्यादा दर्द", "सहन नहीं"],
        bn=["অসহ্য ব্যথা", "প্রচণ্ড ব্যথা"],
        gu=["અસહ્ય દુખાવો", "ખૂબ દુખાવો"],
        kn=["ತುಂಬಾ ನೋವು", "ಅಸಹನೀಯ ನೋವು"],
        ml=["സഹിക്കാൻ പറ്റാത്ത വേദന", "കടുത്ത വേദന"],
        mr=["खूप दुखत", "असह्य वेदना"],
        pa=["ਬਹੁਤ ਦਰਦ", "ਅਸਹਿ ਦਰਦ"],
        ta=["தாங்க முடியாத வலி", "ரொம்ப வலி"],
        te=["భరించలేని నొప్పి", "చాలా నొప్పి"],
    ),
    _rf(
        "lex_wound_opened", U, "Wound or stitches opened",
        latn=["stitches opened", "stitches came out", "wound opened", "wound has opened", "taanke khul", "tanke khul"],
        hi=["टांके खुल", "टाँके खुल", "घाव खुल"],
        bn=["সেলাই খুলে"],
        gu=["ટાંકા ખૂલી"],
        kn=["ಹೊಲಿಗೆ ಬಿಚ್ಚ"],
        ml=["തുന്നൽ പൊട്ട"],
        mr=["टाके उघड"],
        pa=["ਟਾਂਕੇ ਖੁੱਲ੍ਹ"],
        ta=["தையல் பிரிந்த", "தையல் விட்டு"],
        te=["కుట్లు ఊడి", "కుట్లు విడి"],
    ),
    # ---- REVIEW ----
    _rf(
        "lex_fever", R, "Fever mentioned",
        latn=["fever", "temperature", "bukhar", "bukhaar"],
        hi=["बुखार"],
        bn=["জ্বর"],
        gu=["તાવ"],
        kn=["ಜ್ವರ"],
        ml=["പനി"],
        mr=["ताप"],
        pa=["ਬੁਖਾਰ"],
        ta=["காய்ச்சல்"],
        te=["జ్వరం"],
    ),
    _rf(
        "lex_vomiting", R, "Vomiting",
        latn=["vomiting", "throwing up", "vomited", "ulti"],
        hi=["उल्टी"],
        bn=["বমি"],
        gu=["ઉલટી"],
        kn=["ವಾಂತಿ"],
        ml=["ഛർദ്ദി"],
        mr=["उलटी"],
        pa=["ਉਲਟੀ"],
        ta=["வாந்தி"],
        te=["వాంతి"],
    ),
    _rf(
        "lex_dizziness", R, "Dizziness",
        latn=["dizzy", "dizziness", "chakkar"],
        hi=["चक्कर"],
        bn=["মাথা ঘোরা"],
        gu=["ચક્કર"],
        kn=["ತಲೆ ಸುತ್ತು"],
        ml=["തലകറക്കം"],
        mr=["चक्कर"],
        pa=["ਚੱਕਰ"],
        ta=["தலைசுற்றல்", "தலை சுற்று"],
        te=["కళ్ళు తిరుగ", "తల తిరుగ"],
    ),
    _rf(
        "lex_allergy", R, "Possible allergic reaction",
        latn=["allergic reaction", "allergy", "hives", "rash all over"],
        hi=["एलर्जी", "पूरे शरीर पर दाने"],
        bn=["অ্যালার্জি"],
        gu=["એલર્જી"],
        kn=["ಅಲರ್ಜಿ"],
        ml=["അലർജി"],
        mr=["अॅलर्जी", "ऍलर्जी"],
        pa=["ਐਲਰਜੀ"],
        ta=["ஒவ்வாமை", "அலர்ஜி"],
        te=["అలెర్జీ"],
    ),
)

# Negation cues. A cue in the same clause near a symptom marks it as negated ("no fever",
# "बुखार नहीं है"). Cues that are part of the matched phrase itself are ignored, so
# "सांस नहीं आ रही" (can't breathe) still counts.
NEGATIONS: dict[str, tuple[str, ...]] = {
    "latn": ("no", "not", "never", "without", "don't", "dont", "doesn't", "doesnt", "didn't", "didnt",
             "haven't", "havent", "hasn't", "hasnt", "isn't", "isnt", "wasn't", "none", "nahi", "nahin",
             "nai", "na"),
    "hi-IN": ("नहीं", "नही", "ना", "न", "कोई नहीं"),
    "bn-IN": ("না", "নেই", "নাই"),
    "gu-IN": ("નથી", "નહીં", "ના"),
    "kn-IN": ("ಇಲ್ಲ", "ಿಲ್ಲ", "ಬೇಡ"),
    "ml-IN": ("ഇല്ല", "ില്ല"),
    "mr-IN": ("नाही", "नाहीये", "नको"),
    "pa-IN": ("ਨਹੀਂ", "ਨਹੀ", "ਨਾ"),
    "ta-IN": ("இல்லை", "இல்ல", "வில்லை", "இல்லே"),
    "te-IN": ("లేదు", "లేవు", "లేదండి"),
}

# Clause boundaries: punctuation plus contrastive conjunctions ("no fever but chest pain").
CLAUSE_BREAKS: tuple[str, ...] = (
    "but", "however", "although", "lekin", "magar", "par", "पर", "लेकिन", "मगर", "কিন্তু", "પણ", "પરંતુ",
    "ಆದರೆ", "പക്ഷേ", "പക്ഷെ", "पण", "ਪਰ", "ஆனால்", "ஆனா", "కానీ", "కాని",
    # "and" also separates symptoms ("fever hai aur khansi nahi"). Splitting here can only add a flag, never drop one.
    "and", "aur", "और", "आणि",
)
