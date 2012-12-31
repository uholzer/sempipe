<?xml version="1.0" encoding="UTF-8"?>

<!-- Create XHTML 5 from Fresnel result tree. This stylesheet is
suitable for import from another stylesheet, but can also be used
directly. -->

<xsl:stylesheet
    version = "1.0"
    xmlns:xsl   = "http://www.w3.org/1999/XSL/Transform"
    xmlns:fn    = "http://www.w3.org/2005/xpath-functions"
    xmlns:rdf   = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xmlns:foaf  = "http://xmlns.com/foaf/0.1/"
    xmlns:fres  = "http://www.andonyar.com/rec/2012/sempipe/fresnelxml"
    xmlns:xhtml = "http://www.w3.org/1999/xhtml"
    xmlns       = "http://www.w3.org/1999/xhtml"
    exclude-result-prefixes="#all"
>

<xsl:output
     method="xml"
     doctype-system="about:legacy-compat"
     encoding="UTF-8"
     indent="yes" />

<!-- Root element -->

<xsl:template match="/fres:fresnelresult">
    <html>
    <head>
        <title><xsl:value-of select="/fres:fresnelresult/fres:resource/fres:label"/></title>
        <meta charset="utf-8"/>
        <style type="text/css"><![CDATA[
            @namespace html     "http://www.w3.org/1999/xhtml";
            .figure { float: right }
            html|p.otherinterface { font-size: 120%; font-weight: bold }
        ]]></style>
    </head>
    <body>
        <h1><xsl:apply-templates select="/fres:fresnelresult/fres:resource/fres:label"/></h1>
        <xsl:apply-templates select="fres:resource"/>
    </body>
    </html>
</xsl:template>

<!-- fres:resource -->

<xsl:template match="fres:resource[contains(fres:format/@style,'html:dl')]">
    <xsl:apply-templates select="fres:property[contains(fres:format/@style,'out-of-order:before')]"/>
    <dl>
    <xsl:apply-templates select="fres:property[not(contains(fres:format/@style,'out-of-order'))]" mode="dl"/>
    </dl>
    <xsl:apply-templates select="fres:property[contains(fres:format/@style,'out-of-order:after')]"/>
</xsl:template>

<xsl:template match="fres:resource" mode="img">
    <img src="{./@uri}"/>
</xsl:template>

<xsl:template match="fres:resource">
    <xsl:apply-templates select="fres:property"/>
</xsl:template>

<xsl:template match="fres:resource[not(fres:property) and not(string(fres:label))]">
    <!-- Label is missing and no property is present, still we should
         show something. -->
    <xsl:value-of select="@uri"/>
</xsl:template>

<!-- fres:property -->

<xsl:template match="fres:property[contains(fres:format/@style,'figure')]">
    <div class="{fres:format/@style}">
    <xsl:apply-templates select="fres:label"/>
    <xsl:apply-templates select="fres:value"/>
    </div>
</xsl:template>

<xsl:template match="fres:property">
    <xsl:apply-templates select="fres:label"/>
    <xsl:apply-templates select="fres:value"/>
</xsl:template>

<xsl:template match="fres:property" mode="dl">
    <dt><xsl:apply-templates select="fres:label"/></dt>
    <xsl:for-each select="fres:value">
    <dd><xsl:apply-templates select="."/></dd>
    </xsl:for-each>
</xsl:template>

<!-- fres:value -->

<xsl:template match="fres:value[@type='literal']">
    <!-- We need to support arbitrary XML here, therefore we use
    copy-of instead of value-of. -->
    <xsl:copy-of select="(fres:literal|fres:xmlliteral)/child::node()"/>
</xsl:template>

<xsl:template match="fres:value[contains(fres:format/@style,'html:section')]">
    <section>
        <h1><xsl:apply-templates select="fres:resource/fres:label"/></h1>
        <xsl:apply-templates select="fres:resource"/>
    </section>
</xsl:template>

<xsl:template match="fres:value[contains(fres:format/@style,'html:img')]">
    <xsl:apply-templates select="fres:resource" mode="img"/>
</xsl:template>

<xsl:template match="fres:value">
    <xsl:apply-templates select="fres:resource"/>
</xsl:template>

<!-- fres:label -->

<xsl:template match="fres:label">
    <xsl:choose>
    <xsl:when test="not(string(.))">
        <xsl:value-of select="../@uri"/>
    </xsl:when>
    <xsl:otherwise>
        <xsl:value-of select="."/>
    </xsl:otherwise>
    </xsl:choose>
</xsl:template>

</xsl:stylesheet>
