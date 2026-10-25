# Account rollups

## Lost and won counts
Lost_Count__c on Account is a rollup counter kept by OpportunityService.
Won_Count__c works the same way. Both are updated in one bulk update after the loop, never one Account at a time.

## Recalculation
A nightly batch recomputes both counts with an aggregate COUNT() so drift is fixed by morning.
