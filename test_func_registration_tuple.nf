/*
 * FUNC_REGISTRATION Tuple Unpacking Issue - Systematic Test File
 * 
 * This file contains different test approaches to diagnose and fix the tuple unpacking issue.
 * Each test approach is commented and can be uncommented to test.
 * 
 * Problem: Nextflow is unpacking the 9-element tuple when passing to FUNC_REGISTRATION,
 * causing "Invalid method invocation" error with 11 arguments instead of 3.
 * 
 * T2W works correctly with 4-element tuple using identical pattern.
 */

// ============================================================================
// TEST SETUP: Extract the relevant code section from main.nf
// ============================================================================

// This assumes the channels are already created in main.nf:
// - func_reg_tuple: channel of 9-element tuples
// - func_reg_anat_brain: channel of paths (aligned with tuple channel)
// - config_file: value channel (single item)

// ============================================================================
// TEST 1: Baseline - Direct Channel Passing (Current Approach)
// ============================================================================
// Status: ❌ FAILS - Tuple gets unpacked
// Description: Pass channels directly, same pattern as T2W
// Expected: Should work like T2W, but doesn't

/*
def test1_tuple = func_reg_tuple
def test1_anat_brain = func_reg_anat_brain

// Debug output
test1_tuple
    .first()
    .view { tuple_items ->
        println "TEST1: Tuple structure - size=${tuple_items.size()}, type=${tuple_items.getClass().simpleName}"
        println "TEST1: First 4 elements: ${tuple_items.take(4)}"
    }

// This is the current approach that fails
FUNC_REGISTRATION(test1_tuple, test1_anat_brain, config_file)
*/

// ============================================================================
// TEST 2: Verify Tuple Structure at Each Stage
// ============================================================================
// Status: 🔄 DIAGNOSTIC
// Description: Add comprehensive debug output to verify tuple structure

/*
def test2_tuple = func_reg_tuple
def test2_anat_brain = func_reg_anat_brain

println "=== TEST 2: Tuple Structure Verification ==="

// Stage 1: After extraction from multiMap
test2_tuple
    .first()
    .view { tuple_items ->
        println "TEST2 [Stage1]: After multiMap extraction"
        println "TEST2:   Type: ${tuple_items.getClass().simpleName}"
        println "TEST2:   Size: ${tuple_items.size()}"
        println "TEST2:   Is List: ${tuple_items instanceof List}"
        println "TEST2:   Full tuple: ${tuple_items}"
    }

// Stage 2: Before process call
test2_tuple
    .map { tuple_items ->
        println "TEST2 [Stage2]: Before process call"
        println "TEST2:   Tuple preserved: ${tuple_items.size() == 9}"
        tuple_items  // Pass through unchanged
    }
    .set { test2_tuple_verified }

FUNC_REGISTRATION(test2_tuple_verified, test2_anat_brain, config_file)
*/

// ============================================================================
// TEST 3: Compare T2W Pattern Exactly
// ============================================================================
// Status: 🔄 DIAGNOSTIC
// Description: Replicate T2W pattern exactly to see if there are subtle differences

/*
// T2W pattern:
// t2w_reg_input = t2w_reg_multi.tuple  (4-element tuple)
// t1w_ref_for_t2w = t2w_reg_multi.reference
// ANAT_T2W_TO_T1W_REGISTRATION(t2w_reg_input, t1w_ref_for_t2w, config_file)

// FUNC pattern (should be identical):
def test3_tuple = func_reg_multi.tuple  // Extract directly, don't assign to intermediate
def test3_anat_brain = func_reg_multi.anat_brain

// Debug: Compare structure
test3_tuple
    .first()
    .view { tuple_items ->
        println "TEST3: Tuple from multiMap - size=${tuple_items.size()}"
        println "TEST3: T2W has 4 elements, FUNC has 9 - this might be the issue"
    }

FUNC_REGISTRATION(test3_tuple, test3_anat_brain, config_file)
*/

// ============================================================================
// TEST 4: Use into() for Channel Alignment
// ============================================================================
// Status: ⏳ PENDING
// Description: Ensure channels stay synchronized using into()

/*
def test4_tuple = func_reg_tuple
def test4_anat_brain = func_reg_anat_brain

// Use into() to create synchronized copies
test4_tuple.into { test4_tuple_sync1; test4_tuple_sync2 }
test4_anat_brain.into { test4_anat_brain_sync1; test4_anat_brain_sync2 }

// Verify alignment
test4_tuple_sync1
    .first()
    .view { tuple_items ->
        println "TEST4: Synchronized tuple - size=${tuple_items.size()}"
    }

FUNC_REGISTRATION(test4_tuple_sync1, test4_anat_brain_sync1, config_file)
*/

// ============================================================================
// TEST 5: Restructure Tuple (Reduce Size)
// ============================================================================
// Status: ⏳ PENDING
// Description: Combine some elements to reduce tuple from 9 to fewer elements
// Hypothesis: Maybe Nextflow has issues with 9-element tuples specifically

/*
// Option 5A: Combine anat_ses and is_fallback into a single string
def test5a_tuple = func_reg_tuple
    .map { sub, ses, task, run, bold_file, tmean_file, bids_template, anat_ses, is_fallback ->
        def combined_flag = "${anat_ses}_${is_fallback}"  // Combine into string
        [sub, ses, task, run, bold_file, tmean_file, bids_template, combined_flag]  // 8 elements
    }

// Option 5B: Combine bids_template with another element
def test5b_tuple = func_reg_tuple
    .map { sub, ses, task, run, bold_file, tmean_file, bids_template, anat_ses, is_fallback ->
        def combined_info = "${bids_template}|${anat_ses}|${is_fallback}"  // Combine 3 into 1
        [sub, ses, task, run, bold_file, tmean_file, combined_info]  // 7 elements
    }

// Test with 8 elements
FUNC_REGISTRATION(test5a_tuple, func_reg_anat_brain, config_file)
*/

// ============================================================================
// TEST 6: Use join() Instead of Direct Passing
// ============================================================================
// Status: ⏳ PENDING
// Description: Explicitly join channels before passing to process
// Note: This requires restructuring since join() needs matching keys

/*
// Map anat_brain to include keys for joining
def test6_anat_brain_keyed = func_reg_anat_brain
    .map { anat_path ->
        // We need to extract sub/ses from tuple to join properly
        // This is complex - might need to restructure
        [anat_path]  // Placeholder
    }

// Join tuple with anat_brain using sub/ses as keys
def test6_joined = func_reg_tuple
    .map { sub, ses, task, run, bold_file, tmean_file, bids_template, anat_ses, is_fallback ->
        // Create key for joining: [sub, ses]
        [[sub, ses], [sub, ses, task, run, bold_file, tmean_file, bids_template, anat_ses, is_fallback]]
    }
    .join(test6_anat_brain_keyed, by: [0, 1])  // Join by sub, ses
    .map { key, tuple_items, anat_brain ->
        // Reconstruct: tuple_items should be the 9-element tuple
        [tuple_items, anat_brain]
    }
    .multiMap { tuple_items, anat_brain ->
        tuple_ch: tuple_items
        anat_brain_ch: anat_brain
    }
    .set { test6_final }

FUNC_REGISTRATION(test6_final.tuple_ch, test6_final.anat_brain_ch, config_file)
*/

// ============================================================================
// TEST 7: Check Process Definition - Verify Input Declaration
// ============================================================================
// Status: ⏳ PENDING
// Description: Verify process input declaration matches usage
// This test checks if the process definition itself might be the issue

/*
// The process expects:
// input:
//   tuple val(subject_id), val(session_id), val(task_name), val(run), 
//        path(bold_file), path(tmean_file), val(bids_naming_template), 
//        val(anat_session_id), val(is_fallback)
//   path(anat_brain)
//   path config_file

// Test: Create a minimal test tuple to see if process accepts it
def test7_minimal_tuple = Channel.from([['sub1', 'ses1', 'task1', 'run1', 
                                         file('test_bold.nii.gz'), 
                                         file('test_tmean.nii.gz'), 
                                         'test_template', 'ses1', false]])

def test7_minimal_anat = Channel.from([file('test_anat.nii.gz')])

// This should work if the process definition is correct
FUNC_REGISTRATION(test7_minimal_tuple, test7_minimal_anat, config_file)
*/

// ============================================================================
// TEST 8: Wrap Tuple in Another Layer
// ============================================================================
// Status: ⏳ PENDING
// Description: Try wrapping the tuple to prevent unpacking

/*
def test8_tuple = func_reg_tuple
    .map { tuple_items ->
        // Wrap tuple in another list layer
        [[tuple_items]]
    }
    .map { wrapped ->
        // Unwrap - this might help Nextflow recognize it as a tuple
        wrapped[0]
    }

FUNC_REGISTRATION(test8_tuple, func_reg_anat_brain, config_file)
*/

// ============================================================================
// TEST 9: Use combine() with Explicit Tuple Preservation
// ============================================================================
// Status: ⏳ PENDING
// Description: Use combine() but ensure tuple structure is preserved
/*
// Combine anat_brain with config_file first (both are simple paths)
def test9_anat_config = func_reg_anat_brain
    .combine(Channel.fromPath(config_file))
    .set { test9_anat_config_ch }

// Now combine with tuple, but wrap tuple to prevent flattening
def test9_combined = func_reg_tuple
    .map { tuple_items -> 
        println "TEST9: Wrapping tuple - original type: ${tuple_items.getClass().simpleName}, size: ${tuple_items.size()}"
        [tuple_items]  // Wrap to prevent combine() from flattening
    }
    .combine(test9_anat_config_ch)
    .map { wrapped_tuple, anat_config_pair ->
        println "TEST9: After combine - wrapped_tuple type: ${wrapped_tuple.getClass().simpleName}, size: ${wrapped_tuple.size()}"
        // Unwrap: wrapped_tuple is [tuple_items], so get the first element
        def tuple_items = wrapped_tuple instanceof List && wrapped_tuple.size() > 0 ? wrapped_tuple[0] : wrapped_tuple
        println "TEST9: After unwrap - tuple_items type: ${tuple_items.getClass().simpleName}, size: ${tuple_items.size()}"
        
        def (anat_brain, config) = anat_config_pair
        // Ensure tuple_items is a flat list
        def flat_tuple = tuple_items instanceof List ? tuple_items : tuple_items.toList()
        [flat_tuple, anat_brain, config]
    }
    .multiMap { tuple_items, anat_brain, config ->
        println "TEST9: Before multiMap - tuple_items type: ${tuple_items.getClass().simpleName}, size: ${tuple_items.size()}"
        tuple_ch: tuple_items
        anat_brain_ch: anat_brain
        config_ch: config
    }
    .set { test9_final }

println "TEST9: About to call FUNC_REGISTRATION with preserved tuple structure"
FUNC_REGISTRATION(test9_final.tuple_ch, test9_final.anat_brain_ch, test9_final.config_ch)
*/

// ============================================================================
// TEST 10: Split Process Call - Pass Tuple Separately
// ============================================================================
// Status: ⏳ PENDING
// Description: Try passing tuple as a single argument using a different method

/*
// This test checks if we can pass the tuple differently
// Note: This might require process definition changes

def test10_tuple = func_reg_tuple
def test10_anat_brain = func_reg_anat_brain

// Try using into() to ensure proper channel structure
test10_tuple.into { test10_tuple_ch1 }
test10_anat_brain.into { test10_anat_brain_ch1 }

// Verify channels are properly structured
test10_tuple_ch1
    .first()
    .view { tuple_items ->
        println "TEST10: Tuple structure before call - size=${tuple_items.size()}"
    }

FUNC_REGISTRATION(test10_tuple_ch1, test10_anat_brain_ch1, config_file)
*/

// ============================================================================
// TEST 11: Compare with Working T2W - Exact Replication
// ============================================================================
// Status: ⏳ PENDING
// Description: Create a test that exactly replicates T2W pattern but with 9 elements

/*
// T2W working pattern:
// t2w_t1w_joined.multiMap { sub, ses, t2w_file, t2w_bids_template, t1w_file, t1w_bids_template ->
//     tuple: [sub, ses, t2w_file, t2w_bids_template]  // 4 elements
//     reference: t1w_file
// }
// def t2w_reg_input = t2w_reg_multi.tuple
// def t1w_ref_for_t2w = t2w_reg_multi.reference
// ANAT_T2W_TO_T1W_REGISTRATION(t2w_reg_input, t1w_ref_for_t2w, config_file)

// Test: Create a 9-element version of T2W pattern
def test11_input = Channel.from([
    ['sub1', 'ses1', 'task1', 'run1', 
     file('t2w1.nii.gz'), file('t2w1_bids.nii.gz'),
     'template1', 'ses1', false,  // Added 3 more elements to make 9
     file('t1w1.nii.gz'), file('t1w1_bids.nii.gz')]
])

test11_input
    .multiMap { sub, ses, t2w_file, t2w_bids_template, extra1, extra2, extra3, t1w_file, t1w_bids_template ->
        tuple: [sub, ses, t2w_file, t2w_bids_template, extra1, extra2, extra3]  // 7 elements
        reference: t1w_file
    }
    .set { test11_multi }

def test11_tuple = test11_multi.tuple  // 7-element tuple
def test11_ref = test11_multi.reference

// This tests if a 7-element tuple works (intermediate between 4 and 9)
// ANAT_T2W_TO_T1W_REGISTRATION(test11_tuple, test11_ref, config_file)  // Would need to modify process
*/

// ============================================================================
// USAGE INSTRUCTIONS
// ============================================================================
/*
 * To use this test file:
 * 
 * OPTION 1: Run as standalone (requires channel setup)
 * 1. Copy the relevant channel definitions from main.nf (around lines 860-950):
 *    - func_reg_multi (from line 860)
 *    - func_reg_tuple (from line 863)
 *    - func_reg_anat_brain (from line 864)
 *    - config_file (from main workflow)
 * 
 * 2. Include necessary includes/process definitions:
 *    include { FUNC_REGISTRATION } from './modules/functional.nf'
 * 
 * 3. Uncomment the test you want to run
 * 
 * 4. Run: nextflow run test_func_registration_tuple.nf -resume
 * 
 * OPTION 2: Test within main.nf context
 * 1. In main.nf, before the FUNC_REGISTRATION call (around line 949),
 *    comment out the actual call and add:
 *    
 *    // TEST MODE: Uncomment one of the test approaches below
 *    // Then copy the test code from test_func_registration_tuple.nf
 * 
 * 2. Run your normal pipeline: nextflow run main.nf -resume
 * 
 * 4. Document results in FUNC_REGISTRATION_TUPLE_TEST_REPORT.md
 */

// ============================================================================
// CHANNEL EXTRACTION HELPER (for standalone testing)
// ============================================================================
/*
 * If running as standalone, you'll need to set up channels like this:
 * 
 * // Example channel setup (adapt from main.nf):
 * def func_reg_multi = Channel.from([
 *     [
 *         tuple: ['sub1', 'ses1', 'task1', 'run1', 
 *                 file('bold.nii.gz'), file('tmean.nii.gz'), 
 *                 'template', 'ses1', false],
 *         anat_brain: file('anat_brain.nii.gz')
 *     ]
 * ])
 * 
 * def func_reg_tuple = func_reg_multi.tuple
 * def func_reg_anat_brain = func_reg_multi.anat_brain
 * def config_file = file('config.yaml')
 */

