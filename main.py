import pygame
import mido
from mido import get_input_names
from music21 import chord, note
import threading
import time

# === CONFIGURAZIONE COLORI ===
COLOR_BG = (18, 22, 32)           # sfondo scuro-blu notte
COLOR_WHITE = (245, 245, 240)     # tasti bianchi, leggermente avorio
COLOR_BLACK = (30, 30, 30)        # tasti neri scuri
COLOR_HIGHLIGHT = (255, 165, 79)  # arancione acceso (highlight)
COLOR_PRESSED_WHITE = (230, 210, 160)  # tasto bianco premuto, caldo
COLOR_PRESSED_BLACK = (90, 65, 35)      # tasto nero premuto, marrone scuro
COLOR_OUTLINE = (70, 70, 70)      # bordo tasti, grigio scuro
COLOR_BUBBLE_WHITE = (255, 165, 79)   # colore "bolla" per tasti bianchi (arancione)
COLOR_BUBBLE_BLACK = (120, 80, 30)    # colore "bolla" per tasti neri (marrone scuro)
COLOR_TEXT_MAIN = (0, 255, 255)   # ciano brillante per il testo accordo
COLOR_TEXT_SUB = (180, 180, 180)  # grigio chiaro per note
COLOR_TEXT_HINT = (120, 120, 120) # grigio scuro per hint testo

input_ports = get_input_names()
if not input_ports:
    print("⚠️ Nessuna tastiera MIDI trovata.")
    exit(1)
inport = mido.open_input(input_ports[0])

pygame.init()
info = pygame.display.Info()
WIDTH, HEIGHT = info.current_w, info.current_h
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("🎹 FrancyChordie PRO - Pygame Edition")
font_big = pygame.font.SysFont("Arial", 48, bold=True)
font_small = pygame.font.SysFont("Arial", 24)

START_MIDI = 21
END_MIDI = 108
BLACK_KEYS = {1, 3, 6, 8, 10}
NUM_WHITE_KEYS = len([n for n in range(START_MIDI, END_MIDI + 1) if n % 12 not in BLACK_KEYS])
WHITE_KEY_WIDTH = WIDTH / NUM_WHITE_KEYS
WHITE_KEY_HEIGHT = HEIGHT // 3
BLACK_KEY_WIDTH = WHITE_KEY_WIDTH * 2 / 3
BLACK_KEY_HEIGHT = WHITE_KEY_HEIGHT * 2 / 3

pressed_notes = set()
pressed_notes_anim = {}

key_positions = {}
x = 0
for midi_note in range(START_MIDI, END_MIDI + 1):
    if midi_note % 12 not in BLACK_KEYS:
        key_positions[midi_note] = (x, HEIGHT - WHITE_KEY_HEIGHT, WHITE_KEY_WIDTH, WHITE_KEY_HEIGHT, True)
        x += WHITE_KEY_WIDTH

for midi_note in range(START_MIDI, END_MIDI + 1):
    if midi_note % 12 in BLACK_KEYS:
        prev_white = midi_note - 1
        while prev_white not in key_positions and prev_white >= START_MIDI:
            prev_white -= 1
        next_white = midi_note + 1
        while next_white not in key_positions and next_white <= END_MIDI:
            next_white += 1
        if prev_white in key_positions and next_white in key_positions:
            px, py, pw, ph, _ = key_positions[prev_white]
            nx, ny, nw, nh, _ = key_positions[next_white]
            bx = (px + pw + nx) / 2 - BLACK_KEY_WIDTH / 2
            by = HEIGHT - WHITE_KEY_HEIGHT
            key_positions[midi_note] = (bx, by, BLACK_KEY_WIDTH, BLACK_KEY_HEIGHT, False)

abbr = {
    "note": "", "unison": "", "perfect": "", "triad": "",
    "major triad": "", "major third": "", "minor triad": "m",
    "minor third": "m", "diminished triad": "dim", "augmented triad": "aug",
    "dominant seventh chord": "7", "major seventh chord": "maj7",
    "minor seventh chord": "m7", "half-diminished seventh chord": "ø7",
    "diminished seventh chord": "dim7", "minor major seventh chord": "m(maj7)",
    "augmented major seventh chord": "maj7(#5)", "major sixth chord": "6",
    "minor sixth chord": "m6", "dominant ninth chord": "9",
    "major ninth chord": "maj9", "minor ninth chord": "m9",
    "dominant eleventh chord": "11", "major eleventh chord": "maj11",
    "minor eleventh chord": "m11", "dominant thirteenth chord": "13",
    "major thirteenth chord": "maj13", "minor thirteenth chord": "m13",
    "suspended second chord": "sus2", "suspended fourth chord": "sus4",
    "perfect fifth": "5",
}

def recognize_chord(midi_notes):
    if not midi_notes:
        return None, []
    sorted_notes = sorted(midi_notes)
    note_names = [note.Note(n).name for n in sorted_notes]
    full_names = [note.Note(n).nameWithOctave for n in sorted_notes]
    c = chord.Chord(note_names)
    try:
        root = c.root().name
        bass = note.Note(sorted_notes[0]).name
        common_name = c.commonName or c.fullName or ""
        common_name = common_name.lower().strip()
        abbrev = abbr.get(common_name, common_name)
        if bass != root:
            return f"{root}{abbrev}/{bass}", full_names
        else:
            return f"{root}{abbrev}", full_names
    except:
        return "Accordo non riconosciuto", full_names

BPM = 120
speed_multiplier = BPM * 2.25 / 60

def midi_listener():
    while True:
        for msg in inport.iter_pending():
            if msg.type == 'note_on' and msg.velocity > 0:
                pressed_notes.add(msg.note)
                pressed_notes_anim[msg.note] = 0.0
            elif msg.type in ['note_off', 'note_on'] and msg.velocity == 0:
                pressed_notes.discard(msg.note)
                if msg.note in pressed_notes_anim:
                    pressed_notes_anim[msg.note] = 1.0
        time.sleep(0.01)

threading.Thread(target=midi_listener, daemon=True).start()

class NoteBubble:
    def __init__(self, midi_note):
        self.midi_note = midi_note
        x, y, w, h, is_white = key_positions[midi_note]
        self.is_white = is_white
        self.x = x + w / 2
        self.base_y = y
        self.width = w * 0.6
        self.height = 0
        self.speed = speed_multiplier
        self.growing = True
        self.detached = False
        self.current_y = self.base_y

    def update(self):
        if self.growing:
            self.height += self.speed
            self.current_y = self.base_y - self.height
        else:
            if not self.detached:
                self.detached = True
            self.current_y -= self.speed

    def draw(self, surface):
        color = COLOR_BUBBLE_WHITE if self.is_white else COLOR_BUBBLE_BLACK
        surf = pygame.Surface((int(self.width), int(self.height)), pygame.SRCALPHA)
        pygame.draw.rect(surf, color + (255,), (0, 0, int(self.width), int(self.height)), border_radius=6)
        surface.blit(surf, (self.x - self.width / 2, self.current_y))

    def is_dead(self):
        return self.current_y + self.height < 0

note_bubbles = []

def draw_keyboard():
    for note_ in list(pressed_notes_anim.keys()):
        v = pressed_notes_anim[note_]
        if note_ in pressed_notes:
            pressed_notes_anim[note_] = min(v + 0.1, 1.0)
        else:
            pressed_notes_anim[note_] = max(v - 0.05, 0.0)
            if pressed_notes_anim[note_] == 0.0:
                del pressed_notes_anim[note_]

    for midi_note, (x, y, w, h, is_white) in key_positions.items():
        anim = pressed_notes_anim.get(midi_note, 0)
        if is_white:
            color = [int(COLOR_WHITE[i] * (1 - anim) + COLOR_PRESSED_WHITE[i] * anim) for i in range(3)]
            offset_y = anim * 5
            pygame.draw.rect(screen, color, (x, y + offset_y, w, h - offset_y))
            pygame.draw.rect(screen, COLOR_OUTLINE, (x, y + offset_y, w, h - offset_y), 1)
        else:
            color = [int(COLOR_BLACK[i] * (1 - anim) + COLOR_PRESSED_BLACK[i] * anim) for i in range(3)]
            offset_y = anim * 5
            pygame.draw.rect(screen, color, (x, y + offset_y, w, h - offset_y), border_radius=4)

clock = pygame.time.Clock()
running = True

while running:
    screen.fill(COLOR_BG)

    for event in pygame.event.get():
        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            running = False

    draw_keyboard()

    for n in pressed_notes:
        if not any(b.midi_note == n and b.growing for b in note_bubbles):
            note_bubbles.append(NoteBubble(n))

    for bubble in note_bubbles:
        if bubble.growing and bubble.midi_note not in pressed_notes:
            bubble.growing = False
        bubble.update()
        bubble.draw(screen)

    note_bubbles = [b for b in note_bubbles if not b.is_dead()]

    if pressed_notes:
        chord_name, full_notes = recognize_chord(pressed_notes)
        text = font_big.render(f"🎵 {chord_name}", True, COLOR_TEXT_MAIN)
        notes_text = font_small.render(f"Note: {', '.join(full_notes)}", True, COLOR_TEXT_SUB)
    else:
        text = font_big.render("Suona un accordo...", True, COLOR_TEXT_HINT)
        notes_text = font_small.render("", True, COLOR_TEXT_SUB)

    screen.blit(text, (10, 10))
    screen.blit(notes_text, (10, 70))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
