import copy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/input'))
import check_campaign as campaign
import add_ui_hooks as hooks


def carousel(selected):
    return dict(selected=selected, ready=True, x0=60, y0=220, x1=580, y1=460)


def pad(field, bits, mode='menu', token=256, **extra):
    return dict(kind='pad', at=field, buttons=bits, x=0, y=0, ui_field=field-1,
        ui_mode=mode, ui_token=token, source=dict(gesture=True, controller=False,
        touch=False, recipe=False), **extra)


def swipe_rows(field=100, left=True, selected=0, result=1):
    start, end = ([400, 330], [250, 330]) if left else ([250, 330], [400, 330])
    return [dict(kind='swipe', at=field, mode='menu', token=256, queued=True,
        source_field=field-1, carousel=carousel(selected), **{'from': start, 'to': end}),
        pad(field+1, 0x200 if left else 0x100, ui_carousel=carousel(selected)),
        pad(field+7, 0, ui_carousel=carousel(result))]


def entry_rows(field=300):
    token = 256 | (0x217 << 16) | (2 << 32)
    return [dict(kind='click', at=field, mode='menu', token=256, queued=True,
        source_field=field-1, x=320, y=330, carousel=carousel(2)),
        pad(field+1, 0x8000, ui_carousel=carousel(2), ui_items=[
            dict(group=1, id=0, selected=True), dict(group=5, id=2, selected=True,
                x0=240, y0=240, x1=420, y1=460)]),
        pad(field+7, 0, 'campaign_warning', token, ui_items=[])]


def warning_rows(field=400, confirm=False):
    token = 256 | (0x217 << 16) | (2 << 32)
    bounds = dict(x0=160, y0=220, x1=480, y1=386, context=2)
    later = dict(ui_items=[dict(group=2), dict(group=3)]) if confirm else dict(ui_carousel=carousel(2))
    return [dict(kind='click', at=field, mode='campaign_warning', token=token, queued=True,
        source_field=field-1, x=320 if confirm else 50, y=300 if confirm else 100, bounds=bounds),
        pad(field+1, 0x1000 if confirm else 0x4000, 'campaign_warning', token, ui_items=[]),
        pad(field+7, 0, token=262 if confirm else 256, **later)]


def side_rows(field=50, selected=2, target=1):
    delta = (target-selected) % 6
    return [dict(kind='click', at=field, mode='menu', token=256, queued=True,
        source_field=field-1, x=100, y=330, carousel=carousel(selected)),
        pad(field+1, 0x200 if delta <= 3 else 0x100, ui_carousel=carousel(selected), ui_items=[
            dict(group=5, id=selected, selected=True, x0=240, y0=240, x1=420, y1=460),
            dict(group=5, id=target, selected=False, x0=60, y0=240, x1=180, y1=460)]),
        pad(field+7, 0, ui_carousel=carousel(target))]


class CampaignEvidenceTest(unittest.TestCase):
    def test_swipe_needs_direction_release_and_actual_selection_change(self):
        rows = swipe_rows()
        self.assertTrue(campaign.check(rows, [])['gates']['swipe_left'])
        for defect in ('wrong_direction', 'no_change', 'no_release', 'stale', 'controller'):
            bad = copy.deepcopy(rows)
            if defect == 'wrong_direction': bad[1]['buttons'] = 0x100
            elif defect == 'no_change': bad[2]['ui_carousel']['selected'] = 0
            elif defect == 'no_release': bad.pop()
            elif defect == 'stale': bad[0]['source_field'] = 80
            else: bad[1]['source']['controller'] = True
            self.assertFalse(campaign.check(bad, [])['gates']['swipe_left'], defect)

    def test_later_action_or_raw_input_cannot_supply_the_transition(self):
        rows = swipe_rows(); rows[2]['ui_carousel']['selected'] = 0
        rows += swipe_rows(110, selected=0, result=1)
        self.assertFalse(campaign.check(rows, [])['observations'][0]['accepted'])
        self.assertFalse(campaign.check(swipe_rows(), [dict(field=102, buttons=0x200)])['gates']['swipe_left'])

    def test_entry_requires_central_hit_and_original_single_player_selection(self):
        rows = entry_rows()
        self.assertTrue(campaign.check(rows, [])['gates']['selected_entry'])
        rows[1]['ui_items'][0]['selected'] = False
        self.assertFalse(campaign.check(rows, [])['gates']['selected_entry'])
        rows[1]['ui_items'][0]['selected'] = True; rows[0]['x'] = 30
        self.assertFalse(campaign.check(rows, [])['gates']['selected_entry'])

    def test_warning_needs_owned_bounds_no_underlying_input_and_result(self):
        for confirm in (False, True):
            rows = warning_rows(confirm=confirm)
            label = 'warning_continue' if confirm else 'warning_cancel'
            self.assertTrue(campaign.check(rows, [])['gates'][label])
            bad = copy.deepcopy(rows); bad[0].pop('bounds')
            self.assertFalse(campaign.check(bad, [])['gates'][label])
            bad = copy.deepcopy(rows); bad[1]['ui_items'] = [dict(group=5)]
            self.assertFalse(campaign.check(bad, [])['gates'][label])
            bad = copy.deepcopy(rows); bad[2]['ui_token'] = 263
            self.assertFalse(campaign.check(bad, [])['gates'][label])
            if not confirm:
                rows[2]['ui_carousel']['selected'] = 3
                self.assertFalse(campaign.check(rows, [])['gates'][label])

    def test_complete_recipe_does_not_certify_physical_input_or_android(self):
        rows = side_rows() + swipe_rows() + swipe_rows(200, False, 1, 0) + entry_rows() \
            + warning_rows() + entry_rows(500) + warning_rows(600, True) \
            + side_rows(700, 0, 5) + side_rows(800, 5, 0)
        report = campaign.check(rows, [])
        self.assertTrue(report['campaign_recipe_accepted'])
        self.assertFalse(report['physical_input_accepted'])
        self.assertFalse(report['android_accepted'])

    def test_side_click_requires_requested_campaign_and_never_activates(self):
        rows = side_rows()
        self.assertTrue(campaign.check(rows, [])['gates']['side_select'])
        rows[-1]['ui_carousel']['selected'] = 0
        self.assertFalse(campaign.check(rows, [])['gates']['side_select'])
        rows[-1]['ui_carousel']['selected'] = 1; rows[1]['buttons'] = 0x8000
        self.assertFalse(campaign.check(rows, [])['gates']['side_select'])

    def test_wrap_requires_one_step_in_each_direction_and_rejects_long_route(self):
        for selected, target, label in ((0, 5, 'wrap_first_to_last'), (5, 0, 'wrap_last_to_first')):
            rows = side_rows(50, selected, target)
            self.assertTrue(campaign.check(rows, [])['gates'][label])
            rows[1]['buttons'] = 0x200 if selected == 0 else 0x100
            # Even a route with the correct final state cannot pass on the
            # wrong direction or with five acknowledged steps instead of one.
            self.assertFalse(campaign.check(rows, [])['gates'][label])
            for step in range(1, 5):
                current = (selected + (1 if selected == 0 else -1)*step) % 6
                rows += [pad(51+100*step, rows[1]['buttons'], ui_carousel=carousel(current)),
                         pad(57+100*step, 0, ui_carousel=carousel(target))]
            self.assertFalse(campaign.check(rows, [])['gates'][label])

    def test_campaign_patch_requires_the_original_instruction_even_with_matching_hash(self):
        import struct
        rom = bytearray(max(offset for _, _, offset, _, _ in hooks.SITES)+4)
        for _, _, offset, word, _ in hooks.SITES:
            struct.pack_into('>I', rom, offset, word)
        _, pc, offset, word = hooks.CAMPAIGN_WRAP
        struct.pack_into('>I', rom, offset, word)
        with patch.object(hooks, 'ROM_SHA1', hashlib.sha1(rom).hexdigest()):
            result = hooks.hooks(rom)
            self.assertIn(f'vram = 0x{pc:08X}\nvalue = 0', result)
        struct.pack_into('>I', rom, offset, 0)
        with patch.object(hooks, 'ROM_SHA1', hashlib.sha1(rom).hexdigest()):
            with self.assertRaisesRegex(ValueError, 'Campaign wrap instruction anchor changed'):
                hooks.hooks(rom)

    def test_cursor_pick_hooks_require_both_original_instruction_anchors(self):
        import struct
        rom = bytearray(max(offset for _, _, offset, _, _ in hooks.SITES)+4)
        for _, _, offset, word, _ in hooks.SITES:
            struct.pack_into('>I', rom, offset, word)
        _, _, offset, word = hooks.CAMPAIGN_WRAP
        struct.pack_into('>I', rom, offset, word)
        with patch.object(hooks, 'ROM_SHA1', hashlib.sha1(rom).hexdigest()):
            generated = hooks.hooks(rom)
            for kind in range(2):
                self.assertEqual(generated.count(f'sc64_ui_pick(rdram, ctx, {kind});'), 1)
        for _, pc, offset, _, kind in hooks.SITES:
            if not isinstance(kind, str) or not kind.startswith('pick_'):
                continue
            with self.subTest(pc=f'{pc:08X}'):
                damaged = bytearray(rom)
                struct.pack_into('>I', damaged, offset, 0)
                with patch.object(hooks, 'ROM_SHA1', hashlib.sha1(damaged).hexdigest()):
                    with self.assertRaisesRegex(ValueError, f'UI observer instruction anchor changed: {pc:08X}'):
                        hooks.hooks(damaged)

if __name__ == '__main__':
    unittest.main()
