"""
Scene Library — Pre-written cinematic scene descriptions for realistic ad visuals.

Each scene is a complete visual story with:
- Specific setting (time, place, lighting)
- Specific props (realistic details that sell authenticity)
- Specific body language and emotion
- Camera angle and framing
- What NOT to include (negative prompts)

Scenes are organized by taxonomy dimensions (message_type, hook_type, subject_matter)
to enable intelligent matching based on ad content.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Scene:
    """A complete visual scene description for image/video generation."""
    id: str
    name: str
    description: str
    message_types: list[str]  # Which message types this scene fits
    hook_types: list[str]     # Which hook types this scene fits
    subject_matter: str       # Primary subject matter
    tone: str                 # Emotional tone
    time_of_day: str          # morning, afternoon, evening, night
    setting: str              # home_office, clinic, therapy_room, etc.
    negative_prompt: str      # What to avoid


SCENE_LIBRARY: list[Scene] = [
    # =========================================================================
    # PAIN POINT SCENES — showing the problem
    # =========================================================================
    Scene(
        id="late_night_documentation",
        name="Late Night Documentation Struggle",
        description="""A female therapist in her late 30s sits at a small home office desk. It's clearly evening — a digital alarm clock on the desk reads 8:47 PM in red LED digits. The only light is a warm desk lamp casting soft shadows and the cool blue glow of her laptop screen showing a dense clinical note form with many empty fields. There's a cold cup of coffee with a ring stain on the desk, a framed family photo slightly out of focus in the background showing kids at a beach. Her posture shows exhaustion — one hand supporting her chin, elbow on desk, the other hand resting limply on the keyboard. She's wearing comfortable home clothes (a soft cardigan over a casual blouse), not clinical wear. Through the window behind her, the sky is dark. A small stack of folders sits untouched nearby. Shot from slightly above and to the side, like looking over her shoulder. Natural, documentary-style lighting. Shallow depth of field focusing on her tired expression.""",
        message_types=["pain_point", "urgency"],
        hook_types=["scenario", "provocative_claim"],
        subject_matter="clinician_at_work",
        tone="empathetic",
        time_of_day="evening",
        setting="home_office",
        negative_prompt="No text overlays, no logos, no UI elements, no perfectly posed stock photo smiles, no unnaturally bright lighting, no floating objects, no distorted hands or fingers, no impossible anatomy",
    ),
    Scene(
        id="weekend_catchup",
        name="Weekend Documentation Catch-Up",
        description="""A male clinician in his 40s sits at a kitchen table on a Saturday morning, laptop open with clinical notes visible on screen. He's in casual weekend clothes — a faded college t-shirt. Through the window, bright morning sun streams in. In the background, slightly out of focus, his kids are eating cereal at the counter. His wife passes by holding a coffee mug. His expression is resigned, slightly guilty. A smartphone on the table shows notification badges. The kitchen is warm and lived-in — fruit bowl, kids' drawings on the fridge. Shot at eye level, medium-wide to capture the domestic context. The contrast between family Saturday and work laptop is the story.""",
        message_types=["pain_point", "comparison"],
        hook_types=["scenario", "question"],
        subject_matter="clinician_at_work",
        tone="empathetic",
        time_of_day="morning",
        setting="home_kitchen",
        negative_prompt="No text, no logos, no stock photo perfectness, no distorted faces or hands, no impossible room geometry",
    ),
    Scene(
        id="session_gap_stress",
        name="Between Sessions Stress",
        description="""A female therapist in her early 30s sits in a therapy room during a 10-minute gap between sessions. She's in a comfortable therapy chair (not behind a desk), laptop balanced on her knees, typing frantically. A wall clock shows 2:50 PM. Through the door, barely visible, a waiting room with someone sitting. Her body language is tense — shoulders raised, leaning forward. Professional but approachable outfit (soft blazer, no tie). The therapy room has warm tones — a plant, abstract art, two matching chairs. A tissue box on the side table. Natural afternoon light through blinds. Shot from a corner of the room, wide enough to show the cozy therapy setting contrasting with her stressed typing. Documentary feel, not posed.""",
        message_types=["pain_point", "urgency"],
        hook_types=["scenario", "direct_benefit"],
        subject_matter="clinician_at_work",
        tone="urgent",
        time_of_day="afternoon",
        setting="therapy_room",
        negative_prompt="No text, no logos, no patient faces visible, no HIPAA-violating details on screen, no distorted body parts",
    ),
    Scene(
        id="paperwork_pile",
        name="Paperwork Overwhelm",
        description="""Close-up of a desk surface showing the reality of clinical paperwork: a laptop with an EHR system open, several physical intake forms with handwritten notes, a pen, reading glasses, a half-empty water bottle, and sticky notes with patient initials and times. A clinician's hands (female, middle-aged, simple wedding ring) are visible at the edge of frame, one hand on the laptop trackpad, the other holding a pen hovering over a form. The desk lamp casts warm light. The composition tells the story of too much to do. Shallow depth of field with the nearest sticky note in sharp focus showing "3pm - process notes" in handwriting. Shot from above at an angle, documentary style.""",
        message_types=["pain_point", "education"],
        hook_types=["statistic", "scenario"],
        subject_matter="clinician_at_work",
        tone="clinical",
        time_of_day="afternoon",
        setting="office_desk",
        negative_prompt="No faces, no patient names or identifying info visible, no logos, no impossible hand poses, no AI-generated text",
    ),

    # =========================================================================
    # VALUE PROPOSITION SCENES — showing the solution/benefit
    # =========================================================================
    Scene(
        id="relief_moment",
        name="The Relief Moment - Done Early",
        description="""A male clinician in his early 40s closing his laptop with a satisfied, subtle smile — not a grin, just genuine relief. He's in a small private practice office — warm wood desk, two therapy chairs visible in the background, a bookshelf with psychology texts and a few personal items. A small digital clock on the bookshelf shows 5:15 PM in blue digits. He's reaching for his jacket hanging on the back of his chair. Natural late afternoon light comes through wooden blinds, creating warm stripes across the room. The scene conveys "done early for once." Shot at eye level, slightly wide to show the comfortable office. Warm color palette — amber, cream, soft browns. His outfit is professional casual — button-down shirt, no tie.""",
        message_types=["value_prop", "comparison"],
        hook_types=["direct_benefit", "testimonial"],
        subject_matter="clinician_at_work",
        tone="warm",
        time_of_day="afternoon",
        setting="private_practice",
        negative_prompt="No text overlays, no logos, no exaggerated expressions, no stock photo poses, no distorted anatomy, no impossible lighting",
    ),
    Scene(
        id="session_presence",
        name="Fully Present in Session",
        description="""A female therapist in her 50s sitting across from a patient (shown from behind, only shoulder and back of head visible). The therapist is fully engaged — leaning slightly forward, hands relaxed in her lap, making warm eye contact (toward camera, representing patient's POV). No laptop, no notepad in hand — just presence. The therapy room is warm and inviting: soft lighting from a floor lamp, a potted fiddle leaf fig in the corner, abstract calming art on the wall. The therapist wears a comfortable professional outfit — soft sweater, simple jewelry. Late afternoon golden hour light filters through sheer curtains. The composition emphasizes connection and attention. Shot from slightly behind and beside the patient, focusing on the therapist's attentive expression.""",
        message_types=["value_prop", "comparison"],
        hook_types=["direct_benefit", "scenario"],
        subject_matter="patient_interaction",
        tone="warm",
        time_of_day="afternoon",
        setting="therapy_room",
        negative_prompt="No patient face visible, no identifying features of patient, no text, no logos, no technology visible, no distorted faces",
    ),
    Scene(
        id="walking_out_early",
        name="Leaving the Office On Time",
        description="""A female clinician in her mid-30s walking out of a small clinic or private practice building. She's at the door, hand on the handle, turning back with a small satisfied smile. She's wearing a light jacket over professional clothes, holding her bag. Through the glass door behind her, you can see the empty reception area, lights dimming. The sky outside shows late afternoon sun — golden hour, not dark. She looks like she has somewhere good to be. Shot from inside, looking toward the door, capturing her exit moment. Natural lighting mixing the warm interior lights with the golden exterior light.""",
        message_types=["value_prop", "urgency"],
        hook_types=["direct_benefit", "scenario"],
        subject_matter="clinician_at_work",
        tone="warm",
        time_of_day="afternoon",
        setting="clinic_entrance",
        negative_prompt="No text, no logos, no stock photo poses, no distorted body proportions, no impossible architecture",
    ),
    Scene(
        id="family_dinner",
        name="Making It to Family Dinner",
        description="""A family dinner scene shot through a kitchen window from outside, slightly voyeuristic documentary style. Inside, warm lighting reveals a family of four at a dinner table — a male clinician (still in work clothes, sleeves rolled up) passing a dish, kids (around 8 and 12) animated in conversation, spouse laughing. The table has a casual weeknight dinner — pasta, salad, bread. The kitchen is warm and lived-in, not magazine-perfect. A clock on the wall shows 6:30 PM. The clinician's work bag is tossed by the door, laptop inside. Shot from outside through window, shallow focus on the family scene, window frame visible. Evening blue hour light outside contrasts with warm kitchen interior.""",
        message_types=["value_prop", "pain_point"],
        hook_types=["scenario", "direct_benefit"],
        subject_matter="conceptual",
        tone="warm",
        time_of_day="evening",
        setting="home_kitchen",
        negative_prompt="No text, no logos, no stock photo perfect people, no distorted faces or hands, no impossible room layouts",
    ),

    # =========================================================================
    # SOCIAL PROOF / TESTIMONIAL SCENES
    # =========================================================================
    Scene(
        id="peer_recommendation",
        name="Colleague Showing the App",
        description="""Two female clinicians in a clinic break room, one showing the other something on her phone. The one showing the phone has an enthusiastic, "you have to try this" expression. The other is leaning in with genuine curiosity, coffee cup in hand. They're both in professional but comfortable clinical wear. The break room is realistic — small table, microwave visible, a communal coffee maker, someone's lunch bag on the counter. Fluorescent overhead lighting mixed with daylight from a window. Shot at eye level, medium close-up on the two of them, capturing the genuine peer-to-peer recommendation moment. Lunch break energy — relaxed but not off-duty.""",
        message_types=["social_proof", "value_prop"],
        hook_types=["testimonial", "direct_benefit"],
        subject_matter="clinician_at_work",
        tone="warm",
        time_of_day="midday",
        setting="clinic_breakroom",
        negative_prompt="No visible app UI or text on screen, no logos, no stock photo poses, no distorted hands holding phone, no impossible room geometry",
    ),
    Scene(
        id="conference_conversation",
        name="Conference Networking Moment",
        description="""A small group of three clinicians (mixed genders, varied ages 30-55) at what appears to be a professional conference, standing in a hallway during a break. One is gesturing while explaining something, the others nodding with interest. Conference badges visible but text not readable. Cups of coffee in hands. The setting shows conference hallway details — other attendees blurred in background, hotel-style carpet, poster session visible in the distance. Natural fluorescent and window lighting. The conversation has energy — these are colleagues discovering something useful. Shot candidly, like a documentary photographer captured the moment. Professional casual dress code.""",
        message_types=["social_proof", "education"],
        hook_types=["testimonial", "statistic"],
        subject_matter="clinician_at_work",
        tone="authoritative",
        time_of_day="midday",
        setting="conference",
        negative_prompt="No readable text on badges or posters, no logos, no posed stock photo groupings, no distorted faces, no impossible crowd perspectives",
    ),

    # =========================================================================
    # PRODUCT/UI FOCUSED SCENES
    # =========================================================================
    Scene(
        id="phone_recording_session",
        name="Discreet Recording During Session",
        description="""A therapy session from the therapist's perspective. In the foreground, slightly out of focus, is a smartphone lying flat on a side table, screen subtly lit indicating it's active. In the background, in focus, a patient (shown from behind or in profile, face not visible) is speaking, gesturing naturally. The therapy room is warm and professional — two comfortable chairs, soft lighting, a plant, neutral calming art. The composition draws attention to the phone while showing the human connection happening. Shot from the therapist's seated position, low angle, as if the therapist placed the phone down casually. Natural afternoon light through curtains.""",
        message_types=["value_prop", "education"],
        hook_types=["direct_benefit", "scenario"],
        subject_matter="product_ui",
        tone="clinical",
        time_of_day="afternoon",
        setting="therapy_room",
        negative_prompt="No patient face visible, no UI on phone screen, no logos, no text, no distorted proportions, no impossible room angles",
    ),
    Scene(
        id="notes_complete_notification",
        name="Notes Done Notification",
        description="""Close-up of a clinician's hands holding a smartphone. On the screen, a clean notification or message visible (abstract, suggesting "complete" without readable text — perhaps a checkmark icon and blue/green colors). The hands are female, mid-30s, simple professional manicure. Background is blurred but suggests a clinic hallway — other people walking, fluorescent lights. The moment is: just received good news on the phone. A subtle smile visible at the edge of frame (just the chin and lower lip). Shot tight on hands and phone, shallow depth of field. The phone is a modern smartphone, not a specific identifiable brand.""",
        message_types=["value_prop", "urgency"],
        hook_types=["direct_benefit", "statistic"],
        subject_matter="product_ui",
        tone="warm",
        time_of_day="afternoon",
        setting="clinic_hallway",
        negative_prompt="No readable text on phone, no specific app UI, no logos, no brand identifiers, no distorted hands, no impossible screen angles",
    ),

    # =========================================================================
    # COMPARISON / BEFORE-AFTER CONCEPTUAL SCENES
    # =========================================================================
    Scene(
        id="two_desks_comparison",
        name="Side by Side Desk Comparison",
        description="""A split composition showing two desks side by side, clearly the same person's workspace at different times. LEFT SIDE: Chaotic — stacks of folders, sticky notes everywhere, coffee cups (one empty, one half-full and cold), laptop with dense EHR visible, harsh overhead lighting, time showing 8:30 PM on a wall clock. RIGHT SIDE: Clean and organized — laptop closed, neat stack of completed folders, a plant, a photo frame, jacket on chair ready to leave, warm lamp lighting, time showing 5:00 PM. The contrast tells the story without words. Shot from directly above (bird's eye view), symmetric composition. Both desks are realistic clinical workspaces, not magazine-styled.""",
        message_types=["comparison", "value_prop"],
        hook_types=["scenario", "direct_benefit"],
        subject_matter="workflow_comparison",
        tone="clinical",
        time_of_day="mixed",
        setting="office_desk",
        negative_prompt="No text labels, no arrows, no logos, no impossible perspective, no AI-generated text on papers",
    ),
    Scene(
        id="calendar_freedom",
        name="Calendar With Open Evening",
        description="""Close-up of a paper planner or calendar on a desk, showing a week view. The weekdays (Mon-Thu) show dense scheduling — colored blocks, handwritten appointments. Friday afternoon and the weekend are notably empty, with just one handwritten note in the Friday 5pm slot that suggests leaving early (a small smiley face or "dinner w/ [initials]"). A pen rests on the planner. A hand (female, simple ring) is visible at the edge, as if just having written. Soft natural light from a window, casting gentle shadows. The planner is realistic — slightly worn, some pages dog-eared. Shot from above at an angle, documentary style.""",
        message_types=["value_prop", "comparison"],
        hook_types=["direct_benefit", "scenario"],
        subject_matter="workflow_comparison",
        tone="warm",
        time_of_day="afternoon",
        setting="office_desk",
        negative_prompt="No AI-generated text (keep any text minimal and out of focus), no logos, no impossible hand poses, no stock photo perfectness",
    ),

    # =========================================================================
    # CONCEPTUAL / EMOTIONAL SCENES
    # =========================================================================
    Scene(
        id="morning_commute_peace",
        name="Peaceful Morning Commute",
        description="""A clinician (female, late 30s) in the driver's seat of a parked car, having just arrived at work. She's sitting peacefully for a moment before getting out — not stressed, just centered. One hand on the steering wheel, looking out the windshield with a slight smile. Through the windshield, a small clinic or office building is visible in morning light. A coffee cup in the cup holder, her work bag on the passenger seat. The car interior is realistic — some small personal touches (air freshener, photo tucked in visor). Morning golden light streaming through the windshield, creating a warm glow. Shot from the passenger side, capturing her profile and the view ahead.""",
        message_types=["value_prop", "comparison"],
        hook_types=["scenario", "direct_benefit"],
        subject_matter="conceptual",
        tone="warm",
        time_of_day="morning",
        setting="car",
        negative_prompt="No text, no logos on building, no brand identifiers on car, no distorted interior geometry, no impossible reflections",
    ),
    Scene(
        id="evening_reading",
        name="Evening Reading Instead of Working",
        description="""A male clinician in his 50s relaxed in a comfortable armchair in a living room, reading a book (not a clinical text — a novel). He's in casual evening clothes — soft sweater, comfortable pants. A reading lamp provides warm light. Through a window, evening blue hour sky is visible. A cup of tea on the side table, reading glasses on. His expression is peaceful, absorbed in the book. In the background, hints of a lived-in home — family photos, a throw blanket, a dog bed (dog optional). The scene screams "this is how evenings should be." Shot at eye level, slightly wide to capture the cozy domestic scene. Warm color palette throughout.""",
        message_types=["value_prop", "comparison"],
        hook_types=["scenario", "direct_benefit"],
        subject_matter="conceptual",
        tone="warm",
        time_of_day="evening",
        setting="living_room",
        negative_prompt="No text on book cover, no logos, no distorted anatomy, no impossible room geometry, no stock photo perfectness",
    ),
    Scene(
        id="audit_preparation_calm",
        name="Audit Prep Without Stress",
        description="""A clinical supervisor (female, 50s, authoritative but approachable) at a desk with audit preparation materials, but her body language is calm and confident, not stressed. She's reviewing a neat stack of printed documentation, a satisfied expression on her face. The desk is organized — laptop showing a spreadsheet (abstract, no readable data), folders in neat piles, a checklist with visible checkmarks. Office environment with professional decor — credentials on the wall (abstract, not readable), a plant, good lighting. A coffee cup suggests this is a normal workday, not a crisis. Shot at desk level, showing her confident posture and the organized materials.""",
        message_types=["value_prop", "education"],
        hook_types=["direct_benefit", "provocative_claim"],
        subject_matter="clinician_at_work",
        tone="authoritative",
        time_of_day="morning",
        setting="private_practice",
        negative_prompt="No readable text on documents, no logos, no specific credential names visible, no distorted hands or faces, no impossible office layouts",
    ),

    # =========================================================================
    # VIDEO-SPECIFIC SCENES (5-second moments)
    # =========================================================================
    Scene(
        id="video_laptop_close",
        name="Video: Closing Laptop with Relief",
        description="""5-SECOND VIDEO MOMENT: A clinician's hands close a laptop with a satisfying motion. The shot starts tight on the laptop screen (abstract blur, not readable), then the hands enter frame and gently close it. As it closes, the camera pulls back slightly to reveal the clinician's relieved expression — a subtle smile, maybe a small exhale. The background shows a warm office environment going soft-focus. The motion is natural, not slow-mo — real-time relief. Warm afternoon lighting. The laptop is a realistic modern device, no brand visible. Movement: hands close laptop, slight camera pull-back, person's expression revealed.""",
        message_types=["value_prop", "comparison"],
        hook_types=["direct_benefit", "scenario"],
        subject_matter="clinician_at_work",
        tone="warm",
        time_of_day="afternoon",
        setting="private_practice",
        negative_prompt="No text, no logos, no brand identifiers, no impossible hand movements, no glitchy transitions",
    ),
    Scene(
        id="video_phone_notification",
        name="Video: Receiving 'Notes Complete' Alert",
        description="""5-SECOND VIDEO MOMENT: A clinician is walking down a clinic hallway (medium shot, following). Their phone buzzes/lights up in their hand. They glance down, a small smile crosses their face, and they put the phone back in their pocket with a satisfied nod, continuing to walk with slightly more energy. The hallway is realistic — other people passing, typical clinic decor. The phone screen briefly shows light/color suggesting a notification but no readable text. Movement: walking, phone lights up, glance, smile, pocket, continue. Natural motion, documentary style.""",
        message_types=["value_prop", "urgency"],
        hook_types=["direct_benefit", "statistic"],
        subject_matter="product_ui",
        tone="warm",
        time_of_day="afternoon",
        setting="clinic_hallway",
        negative_prompt="No readable text on phone, no logos, no impossible walking motion, no glitchy video artifacts",
    ),
    Scene(
        id="video_leaving_on_time",
        name="Video: Walking Out While Sun is Up",
        description="""5-SECOND VIDEO MOMENT: A clinician pushes open the door of a small clinic, stepping out into late afternoon sunlight. The camera is outside, capturing them as they emerge. They take a breath of fresh air, maybe adjust their bag on their shoulder, and walk toward camera with purpose — not rushing, just leaving at a normal time. The clinic door closes behind them, interior lights visible through the glass. Golden hour lighting catches their face. They might check a watch or phone with a small nod of satisfaction. Movement: door opens, person steps out, door closes, they walk toward camera. Authentic motion.""",
        message_types=["value_prop", "comparison"],
        hook_types=["direct_benefit", "scenario"],
        subject_matter="conceptual",
        tone="warm",
        time_of_day="afternoon",
        setting="clinic_entrance",
        negative_prompt="No text on building, no logos, no impossible door physics, no glitchy movements, no distorted walking",
    ),

    # =========================================================================
    # Additional video scenes (G5) — 7 new scenes for coverage
    # =========================================================================
    Scene(
        id="video_audit_prep_anxiety",
        name="Video: Audit Prep Anxiety",
        description="""5-SECOND VIDEO MOMENT: A clinician sits at a desk surrounded by stacks of paper charts and binders. They pick up a manila folder, flip through a few pages with a stressed expression, then set it back down and rub their eyes or forehead. The office has the feel of end-of-quarter crunch — papers organized into piles, a sticky note reading something (abstract, not readable). Opening frame: wide shot showing the pile of charts. Key action: clinician picking up and flipping through records, stressed expression. Closing frame: they set it down with a sigh, looking at an overloaded desk. Warm but stressed lighting — maybe a desk lamp on in the early morning or evening.""",
        message_types=["pain_point", "urgency"],
        hook_types=["scenario", "question"],
        subject_matter="clinician_at_work",
        tone="urgent",
        time_of_day="morning",
        setting="private_practice",
        negative_prompt="No readable text on papers, no visible file names, no overly dramatic expression, no comedy, no impossible paper physics",
    ),
    Scene(
        id="video_post_session_relief",
        name="Video: Post-Session Relief — Notes Already Done",
        description="""5-SECOND VIDEO MOMENT: A therapist is at the end of a session, watching a patient leave (patient's back visible, no face shown). The therapist opens their laptop to where their notes would normally be waiting — instead, the screen already shows a completed session note (text visible but not readable, blue/white color). Their expression shifts from the slight tension of 'I need to write notes' to genuine surprise and relief — eyebrows raise, a slow smile. They lean back in their chair with a satisfied exhale. Opening: therapist watching patient leave. Key action: opening laptop, seeing notes done. Closing: leaning back with visible relief. Soft afternoon office lighting.""",
        message_types=["value_prop", "pain_point"],
        hook_types=["direct_benefit", "scenario"],
        subject_matter="clinician_at_work",
        tone="empathetic",
        time_of_day="afternoon",
        setting="therapy_office",
        negative_prompt="No readable text on screen, no patient face, no slow-motion cliches, no overly dramatic relief expression, no impossible screen content",
    ),
    Scene(
        id="video_weekend_reclaimed",
        name="Video: Weekend Reclaimed — Family Scene",
        description="""5-SECOND VIDEO MOMENT: A clinician is engaged in a genuine family moment on what appears to be a weekend or evening — sitting on a couch with a child, playing at a kitchen table, or working in a backyard garden. The key visual is: they are PRESENT. Their phone is not in their hand. They're not sneaking looks at a laptop. Opening: the family scene, clinician fully engaged. Key action: a child or partner getting their full attention (maybe pulling their sleeve, being handed something, sharing a laugh). Closing: the clinician smiling, connected. Warm natural home lighting, lived-in environment — not a magazine house. No work props visible.""",
        message_types=["value_prop", "comparison"],
        hook_types=["scenario", "direct_benefit"],
        subject_matter="conceptual",
        tone="warm",
        time_of_day="afternoon",
        setting="home",
        negative_prompt="No laptops or work materials visible, no obvious staging, no stock-photo-perfect home, no child faces in close-up, no awkward posed family moment",
    ),
    Scene(
        id="video_voice_recording_in_car",
        name="Video: Quick Voice Note Between Appointments",
        description="""5-SECOND VIDEO MOMENT: A clinician is parked (engine off) in a small parking lot — could be outside a clinic, a coffee shop, or a patient's house. They pull out their phone, open an app, and speak briefly into it (we see their lips move, hear ambient silence — no speech is audible). A small audio waveform might briefly appear on the screen. They tap a button to stop, glance at the screen with a satisfied nod, and pocket the phone, then grab their bag to get out of the car. The motion is practiced — they've done this before. Mid-day natural light through the car window. Opening: parked car, clinician picks up phone. Key action: speaking into phone, waveform. Closing: satisfied tap, pocket, reaching for bag door.""",
        message_types=["value_prop", "education"],
        hook_types=["scenario", "direct_benefit"],
        subject_matter="product_ui",
        tone="warm",
        time_of_day="day",
        setting="car",
        negative_prompt="No readable text on phone screen, no driving while recording, no staged phone placement, no unrealistic car interior, no distorted hands on phone",
    ),
    Scene(
        id="video_mid_session_quick_note",
        name="Video: Natural Mid-Session Note Capture",
        description="""5-SECOND VIDEO MOMENT: During what appears to be a therapy session, a clinician makes a brief, natural gesture — they glance at a small tablet or phone on the desk beside them and make a single tap or speak one sentence softly toward a microphone icon, then immediately return full attention to the patient (patient's back or profile, not face). The motion is so natural it barely interrupts the session energy. Opening: wide shot of session in progress, therapist and patient across from each other (patient non-identifiable). Key action: therapist's quick natural glance at tablet, gentle tap. Closing: both fully engaged again as if nothing happened. Soft, warm therapy office lighting with a green plant visible.""",
        message_types=["value_prop", "education"],
        hook_types=["direct_benefit", "scenario"],
        subject_matter="patient_interaction",
        tone="warm",
        time_of_day="day",
        setting="therapy_office",
        negative_prompt="No patient face visible, no readable text on any device, no awkward or intrusive note-taking motion, no distracted clinician expression, no phone screen glare",
    ),
    Scene(
        id="video_before_after_desk",
        name="Video: Before/After Desk Transformation",
        description="""5-SECOND VIDEO MOMENT: A quick split cut showing the same desk twice. First half (2-3 seconds): a desk buried in paper charts, sticky notes, binders — a visual representation of the documentation burden. A hand rifling through papers. Second half (2-3 seconds): the same desk, now clean — just a single laptop or tablet open, papers gone, a coffee mug and maybe a plant. A hand resting calmly on the desk. The transformation is immediate (cut, not morph). Same clinician's hands both times for continuity. Same warm office lighting in both shots. Opening frame: chaos. Cut to: order. Closing: single device, calm hands.""",
        message_types=["comparison", "value_prop"],
        hook_types=["direct_benefit", "provocative_claim"],
        subject_matter="workflow_comparison",
        tone="empathetic",
        time_of_day="day",
        setting="private_practice",
        negative_prompt="No readable text on any documents, no logo on laptop, no cartoon-perfect organization in after shot, no magic-wipe transition, no impossible jump cut artifacts",
    ),
]


def get_scene_by_id(scene_id: str) -> Optional[Scene]:
    """Get a specific scene by its ID."""
    for scene in SCENE_LIBRARY:
        if scene.id == scene_id:
            return scene
    return None


def match_scene(
    message_type: str = None,
    hook_type: str = None,
    subject_matter: str = None,
    tone: str = None,
    is_video: bool = False,
) -> Scene:
    """
    Find the best matching scene based on taxonomy attributes.
    
    Priority:
    1. Exact match on subject_matter
    2. Match on message_type
    3. Match on hook_type
    4. Match on tone
    5. Fallback to a sensible default
    
    For video, prefer video-specific scenes (id starts with 'video_').
    """
    candidates = SCENE_LIBRARY.copy()
    
    # For video requests, prefer video-specific scenes
    if is_video:
        video_scenes = [s for s in candidates if s.id.startswith("video_")]
        if video_scenes:
            candidates = video_scenes
    else:
        # For images, exclude video-specific scenes
        candidates = [s for s in candidates if not s.id.startswith("video_")]
    
    def score_scene(scene: Scene) -> int:
        score = 0
        if subject_matter and scene.subject_matter == subject_matter:
            score += 10
        if message_type and message_type in scene.message_types:
            score += 5
        if hook_type and hook_type in scene.hook_types:
            score += 3
        if tone and scene.tone == tone:
            score += 2
        return score
    
    # Score all candidates
    scored = [(score_scene(s), s) for s in candidates]
    scored.sort(key=lambda x: -x[0])  # Highest score first
    
    # Return best match, or a sensible default
    if scored and scored[0][0] > 0:
        return scored[0][1]
    
    # Defaults
    if is_video:
        return get_scene_by_id("video_laptop_close") or SCENE_LIBRARY[-3]
    else:
        return get_scene_by_id("relief_moment") or SCENE_LIBRARY[4]


def get_all_scenes() -> list[Scene]:
    """Return all scenes in the library."""
    return SCENE_LIBRARY.copy()


def get_scenes_by_message_type(message_type: str) -> list[Scene]:
    """Get all scenes that match a given message type."""
    return [s for s in SCENE_LIBRARY if message_type in s.message_types]


def get_scenes_by_subject_matter(subject_matter: str) -> list[Scene]:
    """Get all scenes that match a given subject matter."""
    return [s for s in SCENE_LIBRARY if s.subject_matter == subject_matter]
