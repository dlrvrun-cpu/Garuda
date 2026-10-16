public with sharing class LeadService {
    public static void assignToQueue(List<Lead> leads, Id queueId) {
        for (Lead l : leads) {
            l.OwnerId = queueId;
        }
        update leads;
    }
}
