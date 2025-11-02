import pygame
import mido
import threading
import time
from music21 import chord, note
import fluidsynth

# ================= CONFIG =================
SOUNDFONT_PATH = r"piano.sf2"
SHOW_CHORDS = True
BPM = 60  # battiti per minuto
NOTE_SPEED = BPM * 2.25 / 60  # velocità verticale delle note in pixel/frame

# ================= COLORI =================
COLOR_BG = (20, 22, 30)
COLOR_WHITE = (245, 245, 240)
COLOR_BLACK = (40, 40, 50)
COLOR_PRESSED_WHITE = (255, 210, 120)
COLOR_PRESSED_BLACK = (160, 100, 60)
COLOR_OUTLINE = (70, 70, 85)
COLOR_TEXT_MAIN = (0, 255, 255)
COLOR_TEXT_SUB = (180, 180, 180)
COLOR_BUBBLE_WHITE = (255, 180, 80)
COLOR_BUBBLE_BLACK = (255, 100, 80)

# ================= PYGAME =================
pygame.init()
info = pygame.display.Info()
WIDTH, HEIGHT = info.current_w, info.current_h
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("🎹 FrancyChordie PRO - FluidSynth Edition")
font_big = pygame.font.SysFont("Arial", 48, bold=True)
font_small = pygame.font.SysFont("Arial", 28)

# ================= TASTIERA =================
START_MIDI = 21
END_MIDI = 108
BLACK_KEYS = {1, 3, 6, 8, 10}

white_notes = [n for n in range(START_MIDI, END_MIDI+1) if n % 12 not in BLACK_KEYS]
NUM_WHITE_KEYS = len(white_notes)

white_notes = [n for n in range(START_MIDI, END_MIDI+1) if n % 12 not in BLACK_KEYS]
NUM_WHITE_KEYS = len(white_notes)
WHITE_KEY_WIDTH = WIDTH / (NUM_WHITE_KEYS * 0.96)  # tastiera più larga
WHITE_KEY_HEIGHT = HEIGHT // 3
BLACK_KEY_WIDTH = WHITE_KEY_WIDTH * 0.65
BLACK_KEY_HEIGHT = WHITE_KEY_HEIGHT * 0.6

# ================= MIDI =================
input_ports = mido.get_input_names()
if not input_ports:
    print("⚠️ Nessuna tastiera MIDI trovata.")
    exit(1)
inport = mido.open_input(input_ports[0])

# ================= FLUIDSYNTH =================
fs = fluidsynth.Synth()
fs.start(driver="dsound")
sfid = fs.sfload(SOUNDFONT_PATH)
fs.program_select(0, sfid, 0, 0)

sustain_active = False
pressed_notes = set()
sustained_notes = set()
pressed_notes_anim = {}
note_bubbles = []

# ================= POSIZIONI TASTI =================
key_positions = {}
x = 0
for midi_note in range(START_MIDI, END_MIDI+1):
    if midi_note % 12 not in BLACK_KEYS:
        key_positions[midi_note] = (x, HEIGHT - WHITE_KEY_HEIGHT, WHITE_KEY_WIDTH, WHITE_KEY_HEIGHT, True)
        x += WHITE_KEY_WIDTH

for midi_note in range(START_MIDI, END_MIDI+1):
    if midi_note % 12 in BLACK_KEYS:
        prev_white = midi_note - 1
        while prev_white not in key_positions and prev_white >= START_MIDI:
            prev_white -= 1
        next_white = midi_note + 1
        while next_white not in key_positions and next_white <= END_MIDI:
            next_white += 1
        if prev_white in key_positions and next_white in key_positions:
            px, _, pw, _, _ = key_positions[prev_white]
            nx, _, nw, _, _ = key_positions[next_white]
            bx = (px + pw + nx) / 2 - BLACK_KEY_WIDTH / 2
            by = HEIGHT - WHITE_KEY_HEIGHT
            key_positions[midi_note] = (bx, by, BLACK_KEY_WIDTH, BLACK_KEY_HEIGHT, False)

# ================= ABBREVIAZIONI =================
abbr = {
    "minor triad": "m", "major triad": "", "diminished triad": "dim",
    "augmented triad": "aug", "dominant seventh chord": "7",
    "major seventh chord": "maj7", "minor seventh chord": "m7",
    "half-diminished seventh chord": "ø7", "minor sixth chord": "m6",
    "suspended fourth chord": "sus4", "suspended second chord": "sus2"
}

def recognize_chord(midi_notes):
    if not midi_notes: return None, []
    sorted_notes = sorted(midi_notes)
    note_names = [note.Note(n).name for n in sorted_notes]
    full_names = [note.Note(n).nameWithOctave for n in sorted_notes]
    c = chord.Chord(note_names)
    try:
        root = c.root().name
        bass = note.Note(sorted_notes[0]).name
        common_name = (c.commonName or "").lower().strip()
        abbrev = abbr.get(common_name, common_name)
        if bass != root:
            return f"{root}{abbrev}/{bass}", full_names
        else:
            return f"{root}{abbrev}", full_names
    except:
        return "?", full_names

# ================= NOTE CHE SALGONO =================
class NoteBubble:
    def __init__(self, midi_note):
        self.midi_note = midi_note
        x, y, w, h, is_white = key_positions[midi_note]
        self.is_white = is_white
        self.width = w * (0.8 if is_white else 0.6)
        self.height = 0
        self.y = y  # parte dalla cima del tasto
        self.speed = NOTE_SPEED
        self.growing = True
        self.alive = True
        self.x = x + (w - self.width)/2

    def update(self):
        self.y -= self.speed
        if self.growing:
            self.height += self.speed
        if self.y + self.height < 0:
            self.alive = False

    def stop_growing(self):
        self.growing = False

    def draw(self, surface):
        color = COLOR_BUBBLE_WHITE if self.is_white else COLOR_BUBBLE_BLACK
        rect = pygame.Rect(self.x, self.y, self.width, self.height)
        pygame.draw.rect(surface, color, rect, border_radius=6)
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((255, 255, 255, 30))
        surface.blit(overlay, (self.x, self.y))

# ================= THREAD MIDI =================
def midi_listener():
    global sustain_active
    while True:
        for msg in inport.iter_pending():
            if msg.type=='note_on' and msg.velocity>0:
                pressed_notes.add(msg.note)
                pressed_notes_anim[msg.note]=0.0
                fs.noteon(0,msg.note,msg.velocity)
                note_bubbles.append(NoteBubble(msg.note))
            elif msg.type in ['note_off','note_on'] and msg.velocity==0:
                for bubble in note_bubbles:
                    if bubble.midi_note == msg.note:
                        bubble.stop_growing()
                if sustain_active:
                    sustained_notes.add(msg.note)
                else:
                    fs.noteoff(0,msg.note)
                pressed_notes.discard(msg.note)
            elif msg.type=='control_change' and msg.control==64:
                sustain_active = msg.value>=64
                if not sustain_active:
                    for n in list(sustained_notes):
                        fs.noteoff(0,n)
                        sustained_notes.discard(n)
        time.sleep(0.001)

threading.Thread(target=midi_listener, daemon=True).start()

# ================= DISEGNO TASTIERA =================
def draw_keyboard():
    for note_ in list(pressed_notes_anim.keys()):
        v = pressed_notes_anim[note_]
        if note_ in pressed_notes:
            pressed_notes_anim[note_] = min(v + 0.15, 1.0)
        else:
            pressed_notes_anim[note_] = max(v - 0.07, 0.0)
            if pressed_notes_anim[note_] == 0.0:
                del pressed_notes_anim[note_]

    for midi_note,(x,y,w,h,is_white) in key_positions.items():
        if is_white:
            anim = pressed_notes_anim.get(midi_note,0)
            color = [int(COLOR_WHITE[i]*(1-anim)+COLOR_PRESSED_WHITE[i]*anim) for i in range(3)]
            pygame.draw.rect(screen,color,(x,y,w,h))
            pygame.draw.rect(screen,COLOR_OUTLINE,(x,y,w,h),2)
    for midi_note,(x,y,w,h,is_white) in key_positions.items():
        if not is_white:
            anim = pressed_notes_anim.get(midi_note,0)
            color = [int(COLOR_BLACK[i]*(1-anim)+COLOR_PRESSED_BLACK[i]*anim) for i in range(3)]
            pygame.draw.rect(screen,color,(x,y,w,h),border_radius=6)

# ================= LOOP =================
clock = pygame.time.Clock()
running = True

while running:
    screen.fill(COLOR_BG)

    for event in pygame.event.get():
        if event.type==pygame.QUIT or (event.type==pygame.KEYDOWN and event.key==pygame.K_ESCAPE):
            running=False

    draw_keyboard()

    for bubble in note_bubbles:
        bubble.update()
        bubble.draw(screen)

    note_bubbles = [b for b in note_bubbles if b.alive]

    if SHOW_CHORDS:
        if pressed_notes:
            chord_name, full_notes = recognize_chord(pressed_notes)
            text = font_big.render(f"{chord_name}", True, COLOR_TEXT_MAIN)
            notes_text = font_small.render(", ".join(full_notes), True, COLOR_TEXT_SUB)
        else:
            text = font_big.render("Suona un accordo...", True, COLOR_TEXT_MAIN)
            notes_text = font_small.render("", True, COLOR_TEXT_SUB)
        screen.blit(text,(20,20))
        screen.blit(notes_text,(20,90))

    pygame.display.flip()
    clock.tick(120)

pygame.quit()
fs.delete()
