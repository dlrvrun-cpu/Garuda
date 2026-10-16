public virtual class TriggerHandler {
    private static Set<String> bypassed = new Set<String>();

    public void run() {
        if (bypassed.contains(getName())) {
            return;
        }
        switch on Trigger.operationType {
            when BEFORE_INSERT { beforeInsert(); }
            when BEFORE_UPDATE { beforeUpdate(); }
            when AFTER_INSERT  { afterInsert(); }
            when AFTER_UPDATE  { afterUpdate(); }
        }
    }

    public static void bypass(String handlerName) {
        bypassed.add(handlerName);
    }

    public static void clearBypass(String handlerName) {
        bypassed.remove(handlerName);
    }

    protected virtual void beforeInsert() {}
    protected virtual void beforeUpdate() {}
    protected virtual void afterInsert() {}
    protected virtual void afterUpdate() {}

    private String getName() {
        return String.valueOf(this).substring(0, String.valueOf(this).indexOf(':'));
    }
}
